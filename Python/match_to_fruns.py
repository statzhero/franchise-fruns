"""Match franchise names to FRUNS identifiers.

Matches input franchise names against the FRUNS master file using
sanitization, harmonization, and optional fuzzy matching.
"""

from pathlib import Path
from typing import Literal

import polars as pl
from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from normalize_franchise_names import sanitize_name, harmonize_name


# Data loading -----------------------------------------------------------------


def load_fruns_data() -> pl.DataFrame:
    """Load FRUNS master data from CSV."""
    data_path = Path(__file__).parent.parent / "data" / "fruns-master.csv"
    return pl.read_csv(
        data_path,
        schema_overrides={
            "fruns": pl.Utf8,
            "last_avail_year": pl.Int64,
            "brand_name": pl.Utf8,
            "brand_name_sanitized": pl.Utf8,
            "franchisor": pl.Utf8,
            "franchisor_sanitized": pl.Utf8,
            "naics_code": pl.Utf8,
            "naics_description": pl.Utf8,
        },
    )


def load_harmonize_map() -> pl.DataFrame:
    """Load harmonization mappings from CSV."""
    data_path = Path(__file__).parent.parent / "data" / "harmonize-names.csv"
    return pl.read_csv(
        data_path,
        schema_overrides={"franchise": pl.Utf8, "name_harmonized": pl.Utf8},
        null_values="NA",
    )


# Main function ----------------------------------------------------------------


def match_to_fruns(
    data: pl.DataFrame,
    name_col: str,
    method: Literal["both", "exact", "fuzzy"] = "both",
    fruns_data: pl.DataFrame | None = None,
    harmonize_map: pl.DataFrame | None = None,
    max_distance: float = 0.10,
    verbose: bool = True,
    keep_details: bool = False,
) -> pl.DataFrame:
    """Match franchise names to FRUNS identifiers.

    Args:
        data: DataFrame containing franchise names to match.
        name_col: Column name containing franchise names.
        method: Matching method:
            - "exact": exact matching only (fast, no false positives)
            - "fuzzy": fuzzy matching only (for testing/diagnostics)
            - "both": exact first, then fuzzy for unmatched (recommended)
        fruns_data: FRUNS lookup table (defaults to loading from data/).
        harmonize_map: Harmonization mappings (defaults to loading from data/).
        max_distance: Maximum Jaro-Winkler distance for fuzzy matches (default 0.10).
        verbose: Print match summary and sample fuzzy matches.
        keep_details: Keep diagnostic columns (name_sanitized, match_key,
            fruns_name_sanitized, distance).

    Returns:
        Input data with 'fruns' and 'match_type' columns added.
    """
    if fruns_data is None:
        fruns_data = load_fruns_data()
    if harmonize_map is None:
        harmonize_map = load_harmonize_map()

    prepared = _prepare_input(data, name_col, harmonize_map)

    if method == "exact":
        exact_matches = _find_exact_matches(prepared, fruns_data)
        result = _finalize_matches(prepared, exact_matches, fruns_data, keep_details)
        if verbose:
            _print_summary(result)
        return result

    if method == "fuzzy":
        fuzzy_matches = _match_fuzzy(prepared, fruns_data, max_distance)
        result = _finalize_matches(prepared, fuzzy_matches, fruns_data, keep_details)
        if verbose:
            _print_summary(result, fuzzy_matches)
        return result

    # method == "both": exact first, then fuzzy for unmatched
    exact_matches = _find_exact_matches(prepared, fruns_data)

    matched_ids = set(exact_matches["_row_id"].to_list())
    unmatched = prepared.filter(~pl.col("_row_id").is_in(matched_ids))

    if len(unmatched) == 0:
        fuzzy_matches = pl.DataFrame()
    else:
        fuzzy_matches = _match_fuzzy(unmatched, fruns_data, max_distance)

    all_matches = pl.concat([exact_matches, fuzzy_matches], how="diagonal_relaxed")
    result = _finalize_matches(prepared, all_matches, fruns_data, keep_details)
    if verbose:
        _print_summary(result, fuzzy_matches)
    return result


def _prepare_input(
    data: pl.DataFrame, name_col: str, harmonize_map: pl.DataFrame
) -> pl.DataFrame:
    """Step 1 & 2: Sanitize and harmonize input names."""
    prepared = data.with_row_index("_row_id")
    sanitized = sanitize_name(prepared[name_col])
    harmonized = harmonize_name(sanitized, harmonize_map)
    return prepared.with_columns(
        sanitized.alias("_name_sanitized"),
        harmonized.alias("_match_key"),
    )


def _find_exact_matches(
    data: pl.DataFrame, fruns_data: pl.DataFrame
) -> pl.DataFrame:
    """Step 3a & 3b: Find exact matches on brand and franchisor names."""
    # Filter out rows with null/empty harmonized names
    data_valid = data.filter(
        pl.col("_match_key").is_not_null()
        & (pl.col("_match_key") != "")
    )

    # Step 3a: Exact match on brand name
    fruns_brand = (
        fruns_data.select("fruns", "brand_name_sanitized")
        .drop_nulls(subset=["brand_name_sanitized"])
        .filter(pl.col("brand_name_sanitized") != "")
    )

    # Validate m:1 - brand names should be unique in FRUNS
    assert fruns_brand["brand_name_sanitized"].is_unique().all(), (
        "brand_name_sanitized is not unique in FRUNS data"
    )

    exact_brand = data_valid.join(
        fruns_brand,
        left_on="_match_key",
        right_on="brand_name_sanitized",
        how="inner",
    ).with_columns(pl.lit("exact").alias("match_type"))

    # Step 3b: Exact match on franchisor name (for rows not matched by brand)
    matched_ids = set(exact_brand["_row_id"].to_list())
    unmatched = data_valid.filter(~pl.col("_row_id").is_in(matched_ids))

    fruns_franchisor = (
        fruns_data.select("fruns", "franchisor_sanitized")
        .drop_nulls(subset=["franchisor_sanitized"])
        .filter(pl.col("franchisor_sanitized") != "")
    )

    # Many-to-many join to detect multiple matches
    franchisor_joined = unmatched.join(
        fruns_franchisor,
        left_on="_match_key",
        right_on="franchisor_sanitized",
        how="inner",
    )

    if len(franchisor_joined) == 0:
        return exact_brand

    # Count matches per row
    match_counts = (
        franchisor_joined.group_by("_row_id")
        .len()
        .rename({"len": "_n_matches"})
    )
    franchisor_joined = franchisor_joined.join(match_counts, on="_row_id", how="left")

    # Single franchisor matches - unambiguous
    exact_franchisor = (
        franchisor_joined.filter(pl.col("_n_matches") == 1)
        .with_columns(pl.lit("franchisor").alias("match_type"))
        .drop("_n_matches")
    )

    # Multiple franchisor matches - ambiguous, return null with special match_type
    multiple_ids = (
        franchisor_joined.filter(pl.col("_n_matches") > 1)
        .select("_row_id")
        .unique()
    )
    franchisor_multiple = (
        unmatched.join(multiple_ids, on="_row_id", how="inner")
        .with_columns(
            pl.lit(None).cast(pl.Utf8).alias("fruns"),
            pl.lit("franchisor_multiple").alias("match_type"),
        )
    )

    return pl.concat(
        [exact_brand, exact_franchisor, franchisor_multiple],
        how="diagonal_relaxed",
    )


def _match_fuzzy(
    data: pl.DataFrame, fruns_data: pl.DataFrame, max_distance: float
) -> pl.DataFrame:
    """Step 3c: Find best fuzzy match via Jaro-Winkler distance.

    Uses rapidfuzz.process.extractOne for O(n) performance with C-optimized
    string comparison, replacing the previous O(n*m) nested Python loop.
    """
    unique_input = (
        data["_match_key"].drop_nulls().unique().to_list()
    )
    unique_brands = (
        fruns_data["brand_name_sanitized"].drop_nulls().unique().to_list()
    )

    # Filter empty strings
    unique_input = [name for name in unique_input if name]
    unique_brands = [brand for brand in unique_brands if brand]

    if not unique_input or not unique_brands:
        return pl.DataFrame()

    # Convert max_distance to minimum similarity score (extractOne uses similarity)
    score_cutoff = 1 - max_distance

    # Find best match for each unique input name using optimized extractOne
    best_matches = []
    for name in unique_input:
        result = process.extractOne(
            name,
            unique_brands,
            scorer=JaroWinkler.similarity,
            score_cutoff=score_cutoff,
            processor=None,  # Names are already sanitized
        )

        if result is not None:
            best_brand, score, _ = result
            distance = 1 - score

            # Round to 4 decimal places for consistent comparison with R
            if round(distance, 4) <= max_distance:
                best_matches.append(
                    {
                        "_match_key": name,
                        "_matched_brand": best_brand,
                        "_distance": distance,
                    }
                )

    if not best_matches:
        return pl.DataFrame()

    matches_df = pl.DataFrame(best_matches)

    # Join to get FRUNS
    fruns_lookup = (
        fruns_data.select("brand_name_sanitized", "fruns")
        .unique(subset=["brand_name_sanitized"])
    )

    # Validate m:1
    assert fruns_lookup["brand_name_sanitized"].is_unique().all()

    matches_df = matches_df.join(
        fruns_lookup,
        left_on="_matched_brand",
        right_on="brand_name_sanitized",
        how="left",
    )

    # Join back to original data
    result = data.join(matches_df, on="_match_key", how="inner")
    result = result.with_columns(
        pl.col("_distance")
        .map_elements(lambda d: f"fuzzy_{d:.4f}", return_dtype=pl.Utf8)
        .alias("match_type")
    )

    return result


def _finalize_matches(
    prepared: pl.DataFrame,
    matches: pl.DataFrame,
    fruns_data: pl.DataFrame,
    keep_details: bool = False,
) -> pl.DataFrame:
    """Join matches back to original data."""
    if keep_details:
        keep_cols = ["_row_id", "fruns", "match_type", "_distance"]
        available_cols = [c for c in keep_cols if c in matches.columns]
        matches_subset = (
            matches.select(available_cols) if len(matches) > 0
            else pl.DataFrame(schema={c: pl.Utf8 for c in keep_cols})
        )

        result = prepared.join(matches_subset, on="_row_id", how="left")

        # Canonical sanitized brand name of the matched fruns - unlike the
        # match key, this is guaranteed unique per fruns for all match types
        fruns_names = fruns_data.select(
            "fruns",
            pl.col("brand_name_sanitized").alias("_fruns_name_sanitized"),
        )
        result = result.join(fruns_names, on="fruns", how="left")

        # Place fruns_name_sanitized right after match_type
        cols = result.columns
        cols.remove("_fruns_name_sanitized")
        cols.insert(cols.index("match_type") + 1, "_fruns_name_sanitized")
        result = result.select(cols)

        # Rename internal columns (remove leading underscore)
        rename_map = {c: c[1:] for c in result.columns if c.startswith("_")}
        result = result.rename(rename_map)
    else:
        cols = ["_row_id", "fruns", "match_type"]
        available_cols = [c for c in cols if c in matches.columns]
        matches_subset = (
            matches.select(available_cols) if len(matches) > 0
            else pl.DataFrame(schema={c: pl.Utf8 for c in cols})
        )

        result = prepared.join(matches_subset, on="_row_id", how="left")
        # Drop internal columns
        internal_cols = [c for c in result.columns if c.startswith("_")]
        result = result.drop(internal_cols)

    return result


def _print_summary(
    result: pl.DataFrame, fuzzy_matches: pl.DataFrame | None = None
) -> None:
    """Print match summary to console."""
    match_bucket = (
        pl.when(pl.col("match_type").is_null())
        .then(pl.lit("unmatched"))
        .when(pl.col("match_type").str.starts_with("fuzzy"))
        .then(pl.lit("fuzzy"))
        .otherwise(pl.col("match_type"))
    )

    counts = (
        result.with_columns(match_bucket.alias("match_bucket"))
        .group_by("match_bucket")
        .len()
        .rename({"len": "n"})
        .with_columns((pl.col("n") / pl.col("n").sum() * 100).alias("pct"))
    )

    total = len(result)
    matched = counts.filter(pl.col("match_bucket") != "unmatched")["n"].sum()

    print("\n-- Match Summary --")
    print(f"{total} rows -> {matched} matched ({matched/total*100:.1f}%)")
    print()

    for row in counts.iter_rows(named=True):
        print(f"  {row['match_bucket']:<12} {row['n']:>6}  {row['pct']:>5.1f}%")

    if fuzzy_matches is not None and len(fuzzy_matches) > 0:
        print("\n-- Fuzzy Match Samples --")
        sample = fuzzy_matches.sample(n=min(10, len(fuzzy_matches)))
        sample = sample.sort("_distance")

        for row in sample.iter_rows(named=True):
            name = str(row["_match_key"])[:30].ljust(30)
            brand = str(row["_matched_brand"])[:30].ljust(30)
            dist = row["_distance"]
            print(f"  {name}  ->  {brand}  {dist:.3f}")


if __name__ == "__main__":
    # Example usage
    test_data = pl.DataFrame(
        {
            "franchise_name": [
                "McDonald's Franchising, Inc.",
                "Subway",
                "Some Unknown Franchise",
                "7-Eleven",
            ]
        }
    )

    result = match_to_fruns(test_data, "franchise_name", keep_details=True)
    print("\n-- Result --")
    print(result)
