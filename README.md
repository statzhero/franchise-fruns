# franchise-fruns

Match messy franchise names to standardized [FRUNS](https://www.franchiseregistry.com/fruns/) identifiers.

Franchise names extracted from documents or other sources can be inconsistent, for example: "Subway", "Subway LLC", or "Doctor's Associates Inc." (Subway's franchisor). This repository provides lookup data and matching functions to normalize these names and link them to unique FRUNS codes.

Use it to build a panel dataset or adopt it for other difficult name matching problems.

-   See [franchise-background.md](franchise-background.md) for more information on Franchise Disclosure Documents and FRUNS.
-   See [matching-methodology.md](matching-methodology.md) for implementation details.

## Usage

Clone the repository:

``` bash
git clone https://github.com/statzhero/franchise-fruns.git
```

The matching function `match_to_fruns()` takes a data frame with franchise names and returns it with `fruns` and `match_type` columns added. The `sanitize_name()` function is also available separately for sanitizing names without matching.

### R

``` r
# install.packages(c("dplyr", "readr", "stringr", "stringdist"))
source("R/match_to_fruns.R")

franchises <- tibble::tibble(
  franchise_name = c(
    "1-800-Flowers.com, Inc.",
    "Conroy's",
    "McDonald Franchising, Inc.",
    "Gambinos Pizza",
    "New Cool Franchise"
  )
)

# Default: exact then fuzzy matching (prints match summary)
result <- match_to_fruns(franchises, franchise_name)
#> ── Match Summary ──
#> 5 rows → 4 matched (80%)
#>
#>   exact           3   60.0%
#>   fuzzy           1   20.0%
#>   unmatched       1   20.0%
#>
#> ── Fuzzy Match Samples ──
#>   mcdonald                        →  mcdonalds                       0.022

# Suppress match summary and keep diagnostic columns
match_to_fruns(franchises, franchise_name, verbose = FALSE, keep_details = TRUE)
#> # A tibble: 5 × 8
#>   franchise_name             name_sanitized   name_harmonized fruns   match_type
#>   <chr>                      <chr>            <chr>           <chr>   <chr>
#> 1 1-800-Flowers.com, Inc.    1 800 flowerscom 1 800 flowers   10012   exact
#> 2 Conroy's                   conroys          1 800 flowers   10012   exact
#> 3 McDonald Franchising, Inc. mcdonald         mcdonald        12321   fuzzy_0.0222
#> 4 Gambinos Pizza             gambinos pizza   gambinos pizza  FN25002 exact
#> 5 New Cool Franchise         new cool         new cool        NA      NA
#> # ℹ 2 more variables: matched_brand <chr>, distance <dbl>
```

### Python

``` python
# pip install pandas rapidfuzz
import pandas as pd
from match_to_fruns import match_to_fruns

franchises = pd.DataFrame({
    "franchise_name": [
        "1-800-Flowers.com, Inc.",
        "Conroy's",
        "McDonald Franchising, Inc.",
        "Gambinos Pizza",
        "New Cool Franchise"
    ]
})

result = match_to_fruns(franchises, "franchise_name")
#> ── Match Summary ──
#> 5 rows → 4 matched (80.0%)
#>
#>   exact             3   60.0%
#>   fuzzy             1   20.0%
#>   unmatched         1   20.0%
#>
#> ── Fuzzy Match Samples ──
#>   mcdonald                        →  mcdonalds                       0.022

# Suppress match summary and keep diagnostic columns
result = match_to_fruns(franchises, "franchise_name", verbose=False, keep_details=True)
```

### Stata

``` stata
// ssc install matchit
do "Stata/match_to_fruns.do"

clear
input str50 franchise_name
"1-800-Flowers.com, Inc."
"Conroy's"
"McDonald Franchising, Inc."
"Gambinos Pizza"
"New Cool Franchise"
end

// Default: exact matching, then fuzzy for unmatched
match_to_fruns franchise_name

// Exact matching only
match_to_fruns franchise_name, method(exact)

// Suppress match summary and keep diagnostic columns
match_to_fruns franchise_name, quiet keep_details
```

## Matching algorithm

The algorithm applies three steps:

1.  **Sanitizing**: Lowercase, remove punctuation, remove corporate suffixes (Inc, LLC), remove franchise terms (Franchising, Franchisor), and remove geographic markers (International, USA).

2.  **Harmonizing**: Map known variants and misspellings to canonical names via `data/harmonize-names.csv`. Generic names (e.g., "pizza", "plumber") map to `NA` to prevent false positives.

3.  **Matching**: First try exact match on brand name, then on franchisor name. For the remaining unmatched names, the fuzzy match uses the Jaro-Winkler distance (threshold ≤ 0.10).

## Parameters

| Parameter | Default | Description |
|------------------------|--------------------|----------------------------|
| `method` | `"both"` | `"exact"`, `"fuzzy"`, or `"both"` (exact first, then fuzzy) |
| `max_distance` | `0.10` | Maximum Jaro-Winkler distance for fuzzy matches |
| `verbose` | `TRUE` | Print match summary and sample fuzzy matches |
| `keep_details` | `FALSE` | Return diagnostic columns (sanitized name, distance) |

## Match types

| `match_type` | Description |
|-------------------------------------|-----------------------------------|
| `exact` | Matched on normalized brand name |
| `franchisor` | Matched on normalized franchisor name (must be unique) |
| `franchisor_multiple` | Multiple franchises share this franchisor (FRUNS = `NA`) |
| `fuzzy_XXXX` | Fuzzy match with distance (e.g., `fuzzy_0.0312`) |
| `NA` | No match found |

## Data

The repository includes three datasets in `data/`.

### fruns-master.csv

The primary lookup table linking franchise brands to FRUNS identifiers. Each row represents a franchise (brand).

| Column | Description |
|-------------------------|----------------------------------------------|
| `fruns` | FRUNS identifier (5-digit official or FN-prefixed extension) |
| `last_avail_year` | Most recent year the franchise appeared in FDD filings |
| `brand_name` | Consumer-facing brand name |
| `brand_name_sanitized` | Normalized brand name for matching |
| `franchisor` | Legal franchisor entity name |
| `franchisor_sanitized` | Normalized franchisor name for matching |
| `naics_code` | 6-digit NAICS industry code |
| `naics_description` | NAICS industry description |

### harmonize-names.csv

Manual mappings that convert name variants or misspellings to a unified name. The matching algorithm applies these after sanitizing but before lookup.

| Column            | Description                      |
|-------------------|----------------------------------|
| `franchise`       | Input name (sanitized form)      |
| `name_harmonized` | Unified name to use for matching |

> [!NOTE] 
Rows mapping to `NA` represent generic names (e.g., "pizza", "plumber") that would produce false positives.

### publicly-traded-franchisors-fruns.csv

Links publicly traded companies to their franchise brands. Use this to connect franchise data to SEC filings or financial databases.

| Column        | Description                                  |
|---------------|----------------------------------------------|
| `cik`         | SEC Central Index Key for the parent company |
| `corporation` | Legal name of the publicly traded parent     |
| `brand`       | Franchise brand name                         |
| `fruns`       | FRUNS identifier                             |

Multi-brand franchisors appear as multiple rows (e.g., Anywhere Real Estate owns Century 21, Coldwell Banker, and Better Homes and Gardens Real Estate).

## Contributing

Contributions are welcome:

-   **Missing franchises**: Add new FRUNS entries to `data/fruns-master.csv` for franchises not in the lookup table, following our scheme ('FN' + 5-digit number).
-   **Name harmonization**: Improve `data/harmonize-names.csv` with additional mappings
-   **Bug reports**: Open an issue for matching errors or implementation problems

Then, document changes in [NEWS.md](NEWS.md).

## References

-   [FRUNS (Franchise Registry)](https://www.franchiseregistry.com/fruns/)
-   [Atz (2025)](https://doi.org/10.2139/ssrn.5381656): More background on the US franchise market