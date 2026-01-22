# Matching Methodology

This document describes how franchise names are matched to FRUNS identifiers. The algorithm is implemented in [R](https://www.r-project.org/), [Python](https://www.python.org/), and [Stata](https://www.stata.com/).

## Data sources

**fruns-master.csv** is the lookup table containing current and historical brand names, franchisor names, and their sanitized variants. Each row has a unique FRUNS identifier. When there is no official FRUNS, we add new IDs with `FN` prefix + 2-digit year + sequence (e.g., `FN25001`).

**harmonize-names.csv** provides mappings for known name variants and intentional exclusions.

> [!NOTE] 
> We map generic names (e.g., "pizza", "plumber"), and unknown franchises, to `NA` to avoid false positives.

## The three-step matching process

### Step 1: Sanitizing

Input names are normalized to lowercase ASCII, with punctuation removed and corporate/franchise suffixes stripped (Inc, LLC, Franchising, International, etc.). If stripping leaves a name too short, terms are added back. The minimum length defaults to 4 characters, so "KFC" stays as "kfc" and "ATL Franchising" becomes "atl franchising" rather than just "atl".

Example: "McDonald's Franchising, Inc." → "mcdonalds"

See `R/normalize_franchise_names.R`, `Python/normalize_franchise_names.py`, and `Stata/normalize_franchise_names.do` for implementation details.

### Step 2: Harmonizing

After sanitizing, names are checked against `harmonize-names.csv`. Known variants map to canonical names (e.g., a legacy abbreviation mapping to the current brand name). We map generic names (e.g., "pizza", "plumber"), and unknown franchises, to `NA` to avoid false positives.

### Step 3: Matching

Matching proceeds in three stages, stopping at the first successful match:

**3a. Exact match on brand name**: The harmonized name is matched against `brand_name_sanitized` in the FRUNS master. Brand names should be unique (there is an enforced many-to-one relationship ).

**3b. Exact match on franchisor name**: If there is no brand match, the harmonized name is matched against `franchisor_sanitized`. Unfortunately, multiple brands may share a franchisor name (many-to-many relationship). When a single FRUNS matches, that result is returned with `match_type = "franchisor"`. When multiple FRUNS match, no unique identifier can be assigned and the result is `match_type = "franchisor_multiple"` with NA for FRUNS.

**3c. Fuzzy matching**: For names still unmatched, the algorithm finds the closest brand name using Jaro-Winkler similarity with prefix scaling factor p = 0.1. Matches are accepted when distance ≤ 0.10 (equivalently, similarity ≥ 0.90). The match type encodes the distance (e.g., `fuzzy_0.0312`).

Jaro-Winkler suits franchise names because brands typically share identical prefixes with minor suffix variations ("Sit Still" vs. "Sit Still Kids Salon"). The algorithm tolerates small differences (typos, abbreviations) while rejecting unrelated strings.

The 0.10 distance threshold was chosen empirically.

## Implementation details

R uses [`stringdist::amatch()`](https://cran.r-project.org/package=stringdist) with `method = "jw", p = 0.1`. Python uses [`rapidfuzz.process.extractOne()`](https://rapidfuzz.github.io/RapidFuzz/) with `JaroWinkler.similarity`. Stata uses [`matchit`](https://ideas.repec.org/c/boc/bocode/s457992.html) with `similmethod(jw)`. All implementations apply a 0.10 distance threshold as default.

Matches exactly on the 0.10 boundary may differ across implementations due to floating-point handling and how the packages handle tie-breaking. In practice, these edge cases are rare.

The matching function returns the input data with two additional columns: 
- `fruns`: The matched FRUNS identifier (NA if unmatched or ambiguous) 
- `match_type`: One of `exact`, `franchisor`, `franchisor_multiple`, `fuzzy_XXXX`, or NA

With the argument `keep_details = TRUE`, diagnostic columns are also returned: `name_sanitized`, `name_harmonized`, `matched_brand`, and `distance`.