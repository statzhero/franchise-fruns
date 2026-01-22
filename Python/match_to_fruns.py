"""Match franchise names to FRUNS identifiers.

Matches input franchise names against the FRUNS master file using
sanitization, harmonization, and optional fuzzy matching.
"""

from pathlib import Path
from typing import Literal

import pandas as pd
from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from normalize_franchise_names import sanitize_name, harmonize_name


# Data loading -----------------------------------------------------------------


def load_fruns_data() -> pd.DataFrame:
    """Load FRUNS master data from CSV."""
    data_path = Path(__file__).parent.parent / "data" / "fruns-master.csv"
    return pd.read_csv(
        data_path,
        dtype={
            "fruns": "str",
            "last_avail_year": "Int64",
            "brand_name": "str",
            "brand_name_sanitized": "str",
            "franchisor": "str",
            "franchisor_sanitized": "str",
            "naics_code": "str",
            "naics_description": "str",
            "brand_name_sanitized_alt": "str",
        },
    )


def load_harmonize_map() -> pd.DataFrame:
    """Load harmonization mappings from CSV."""
    data_path = Path(__file__).parent.parent / "data" / "harmonize-names.csv"
    return pd.read_csv(
        data_path,
        dtype={"franchise": "str", "name_harmonized": "str"},
    )


# Main function ----------------------------------------------------------------


def match_to_fruns(
    data: pd.DataFrame,
    name_col: str,
    method: Literal["both", "exact", "fuzzy"] = "both",
    fruns_data: pd.DataFrame | None = None,
    harmonize_map: pd.DataFrame | None = None,
    max_distance: float = 0.10,
    verbose: bool = True,
    keep_details: bool = False,
) -> pd.DataFrame:
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
        keep_details: Keep diagnostic columns (name_sanitized, name_harmonized, distance).

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
        result = _finalize_matches(prepared, exact_matches, keep_details)
        if verbose:
            _print_summary(result)
        return result

    if method == "fuzzy":
        fuzzy_matches = _match_fuzzy(prepared, fruns_data, max_distance)
        result = _finalize_matches(prepared, fuzzy_matches, keep_details)
        if verbose:
            _print_summary(result, fuzzy_matches)
        return result

    # method == "both": exact first, then fuzzy for unmatched
    exact_matches = _find_exact_matches(prepared, fruns_data)

    matched_ids = set(exact_matches["_row_id"])
    unmatched = prepared[~prepared["_row_id"].isin(matched_ids)].copy()

    if len(unmatched) == 0:
        fuzzy_matches = pd.DataFrame()
    else:
        fuzzy_matches = _match_fuzzy(unmatched, fruns_data, max_distance)

    all_matches = pd.concat([exact_matches, fuzzy_matches], ignore_index=True)
    result = _finalize_matches(prepared, all_matches, keep_details)
    if verbose:
        _print_summary(result, fuzzy_matches)
    return result


def _prepare_input(
    data: pd.DataFrame, name_col: str, harmonize_map: pd.DataFrame
) -> pd.DataFrame:
    """Step 1 & 2: Sanitize and harmonize input names."""
    prepared = data.copy()
    prepared["_row_id"] = range(len(prepared))
    prepared["_name_sanitized"] = sanitize_name(prepared[name_col])
    prepared["_name_harmonized"] = harmonize_name(
        prepared["_name_sanitized"], harmonize_map
    )
    return prepared


def _find_exact_matches(
    data: pd.DataFrame, fruns_data: pd.DataFrame
) -> pd.DataFrame:
    """Step 3a & 3b: Find exact matches on brand and franchisor names."""
    # Filter out rows with NA/empty harmonized names (like R's na_matches = "never")
    data_valid = data[data["_name_harmonized"].notna() & (data["_name_harmonized"] != "")]

    # Step 3a: Exact match on brand name
    # Brand names should be unique in FRUNS - validate="m:1" errors if not
    fruns_brand = fruns_data[["fruns", "brand_name_sanitized"]].dropna(subset=["brand_name_sanitized"])
    fruns_brand = fruns_brand[fruns_brand["brand_name_sanitized"] != ""]

    exact_brand = data_valid.merge(
        fruns_brand,
        left_on="_name_harmonized",
        right_on="brand_name_sanitized",
        how="inner",
        validate="m:1",
    )
    exact_brand["match_type"] = "exact"
    exact_brand = exact_brand.drop(columns=["brand_name_sanitized"])

    # Step 3b: Exact match on franchisor name (for rows not matched by brand)
    # Multiple brands may share a franchisor - handle explicitly
    matched_ids = set(exact_brand["_row_id"])
    unmatched = data_valid[~data_valid["_row_id"].isin(matched_ids)]

    fruns_franchisor = fruns_data[["fruns", "franchisor_sanitized"]].dropna(subset=["franchisor_sanitized"])
    fruns_franchisor = fruns_franchisor[fruns_franchisor["franchisor_sanitized"] != ""]

    # Many-to-many merge to detect multiple matches
    franchisor_joined = unmatched.merge(
        fruns_franchisor,
        left_on="_name_harmonized",
        right_on="franchisor_sanitized",
        how="inner",
    )

    if len(franchisor_joined) == 0:
        return exact_brand

    # Count matches per row
    match_counts = franchisor_joined.groupby("_row_id").size().reset_index(name="_n_matches")
    franchisor_joined = franchisor_joined.merge(match_counts, on="_row_id", how="left")

    # Single franchisor matches - unambiguous
    exact_franchisor = franchisor_joined[franchisor_joined["_n_matches"] == 1].copy()
    exact_franchisor["match_type"] = "franchisor"
    exact_franchisor = exact_franchisor.drop(columns=["franchisor_sanitized", "_n_matches"])

    # Multiple franchisor matches - ambiguous, return NA with special match_type
    # Get distinct row IDs that had multiple matches, then join back to input data
    multiple_ids = franchisor_joined.loc[
        franchisor_joined["_n_matches"] > 1, "_row_id"
    ].unique()
    franchisor_multiple = unmatched[unmatched["_row_id"].isin(multiple_ids)].copy()
    franchisor_multiple["fruns"] = pd.NA
    franchisor_multiple["match_type"] = "franchisor_multiple"

    return pd.concat([exact_brand, exact_franchisor, franchisor_multiple], ignore_index=True)


def _match_fuzzy(
    data: pd.DataFrame, fruns_data: pd.DataFrame, max_distance: float
) -> pd.DataFrame:
    """Step 3c: Find best fuzzy match via Jaro-Winkler distance.

    Uses rapidfuzz.process.extractOne for O(n) performance with C-optimized
    string comparison, replacing the previous O(n×m) nested Python loop.
    """
    unique_input = data["_name_harmonized"].dropna().unique()
    unique_brands = fruns_data["brand_name_sanitized"].dropna().unique().tolist()

    # Filter empty strings
    unique_input = [name for name in unique_input if name]
    unique_brands = [brand for brand in unique_brands if brand]

    if not unique_input or not unique_brands:
        return pd.DataFrame()

    # Convert max_distance to minimum similarity score (extractOne uses similarity)
    # JaroWinkler.similarity returns 0-1, so score_cutoff is also 0-1
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
            distance = 1 - score  # Convert similarity back to distance

            # Round to 4 decimal places for consistent comparison with R
            if round(distance, 4) < max_distance:
                best_matches.append(
                    {
                        "_name_harmonized": name,
                        "_matched_brand": best_brand,
                        "_distance": distance,
                    }
                )

    if not best_matches:
        return pd.DataFrame()

    matches_df = pd.DataFrame(best_matches)

    # Join to get FRUNS
    matches_df = matches_df.merge(
        fruns_data[["brand_name_sanitized", "fruns"]].drop_duplicates(),
        left_on="_matched_brand",
        right_on="brand_name_sanitized",
        how="left",
        validate="m:1",
    ).drop(columns=["brand_name_sanitized"])

    # Join back to original data
    result = data.merge(matches_df, on="_name_harmonized", how="inner")
    result["match_type"] = result["_distance"].apply(lambda d: f"fuzzy_{d:.4f}")

    return result


def _finalize_matches(
    prepared: pd.DataFrame, matches: pd.DataFrame, keep_details: bool = False
) -> pd.DataFrame:
    """Join matches back to original data."""
    if keep_details:
        keep_cols = ["_row_id", "fruns", "match_type", "_matched_brand", "_distance"]
        available_cols = [c for c in keep_cols if c in matches.columns]
        matches_subset = matches[available_cols].copy() if len(matches) > 0 else pd.DataFrame(columns=available_cols)

        result = prepared.merge(matches_subset, on="_row_id", how="left")
        # Rename internal columns (remove leading underscore)
        rename_map = {c: c[1:] for c in result.columns if c.startswith("_")}
        result = result.rename(columns=rename_map)
    else:
        cols = ["_row_id", "fruns", "match_type"]
        available_cols = [c for c in cols if c in matches.columns]
        matches_subset = matches[available_cols].copy() if len(matches) > 0 else pd.DataFrame(columns=cols)

        result = prepared.merge(matches_subset, on="_row_id", how="left")
        # Drop internal columns
        internal_cols = [c for c in result.columns if c.startswith("_")]
        result = result.drop(columns=internal_cols)

    return result


def _print_summary(
    result: pd.DataFrame, fuzzy_matches: pd.DataFrame | None = None
) -> None:
    """Print match summary to console."""
    result = result.copy()
    result["match_bucket"] = result["match_type"].apply(
        lambda x: "unmatched"
        if pd.isna(x)
        else ("fuzzy" if str(x).startswith("fuzzy") else x)
    )

    counts = result.groupby("match_bucket").size().reset_index(name="n")
    counts["pct"] = counts["n"] / counts["n"].sum() * 100

    total = len(result)
    matched = counts[counts["match_bucket"] != "unmatched"]["n"].sum()

    print("\n── Match Summary ──")
    print(f"{total} rows → {matched} matched ({matched/total*100:.1f}%)")
    print()

    for _, row in counts.iterrows():
        print(f"  {row['match_bucket']:<12} {row['n']:>6}  {row['pct']:>5.1f}%")

    if fuzzy_matches is not None and len(fuzzy_matches) > 0:
        print("\n── Fuzzy Match Samples ──")
        sample = fuzzy_matches.sample(n=min(10, len(fuzzy_matches)))
        sample = sample.sort_values("_distance")

        for _, row in sample.iterrows():
            name = str(row["_name_harmonized"])[:30].ljust(30)
            brand = str(row["_matched_brand"])[:30].ljust(30)
            dist = row["_distance"]
            print(f"  {name}  →  {brand}  {dist:.3f}")


if __name__ == "__main__":
    # Example usage
    test_data = pd.DataFrame(
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
    print("\n── Result ──")
    print(result)
