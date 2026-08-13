# franchise-fruns News

## 2026-08-13

### Renamed diagnostic columns in `match_to_fruns()` output

With `keep_details`, the matcher now returns `match_key` (formerly
`name_harmonized`) and `fruns_name_sanitized` (formerly `matched_brand`,
which was only filled for fuzzy matches). `fruns_name_sanitized` is the
sanitized brand name of the matched franchise, filled for every
successful match. Unlike the match key, it is guaranteed unique per
FRUNS, so use it (or join `brand_name` from `fruns-master.csv` on
`fruns`) when you need one standardized name per franchise. Column
names in `harmonize-names.csv` are unchanged.

### Stata: fixed fuzzy matching after the franchisor step

The franchisor matching step modified the FRUNS frame in place and
dropped the brand column that the fuzzy step needs. The step now works
on a copy of the frame.

### Fixes to `harmonize-names.csv`

- Corrected `1 800 flowers i conroy s` to `1 800 flowers i conroys`.
  The sanitizer removes apostrophes without leaving a space, so the old
  key could never occur.
- Removed a duplicate `ramada` row.
- Added `pizza` as a blocked generic name. The README cites it as the
  blocking example, but the row was missing, so "Pizza" fuzzy-matched
  to "Pizza 9".

## 2026-05-26

### 412 name variants added to `harmonize-names.csv`

Bulk addition of harmonization rules generated from unmatched names in
the franchise-metadata pipeline. Mostly long-form FDD names with
trailing descriptors, regional qualifiers, or multi-brand listings
(e.g., "togos restaurant" to "togos", "jan pro northwest" to "jan pro
cleaning disinfecting"). A smaller share are spelling variants and
alias corrections.

## 2026-03-04

### New name mappings added to `harmonize-names.csv`

| Former Name               | Current Name                  | Type  |
|---------------------------|-------------------------------|-------|
| Salon Plaza               | My Salon Suite                | aka   |

Subtracted "Salon Plaza" from `fruns-master.csv` as it is always in the same FDD as "My Salon Suite".

Added a substantial number of "aka"s to `harmonize-names.csv` that do not have significant repercussions.

## 2026-02-05

### New name mappings added to `harmonize-names.csv`

| Former Name               | Current Name                  | Type  |
|---------------------------|-------------------------------|-------|
| Value Place               | Woodspring Suites             | fka   |

Subtracted "Value Place" from `fruns-master.csv` in accordance with the rebranding that underwent in 2015 

Likewise added a substantial number of "aka"s to the `harmonize-names.csv` that do not have significant repurcussions.

## 2026-02-02

### New name mapping added to `harmonize-names.csv`

| Former Name               | Current Name                  | Type  |
|---------------------------|-------------------------------|-------|
| Rainbow Station           | Leafspring School             | fka   |
| Huntington School Services| Huntington Learning Center    | aka   |

Reconsidered an entry for Chi-Chi's, a franchise that's currently listed as a Jack in the Box brand (TBC).

## 2026-01-22

### New name mappings added to `harmonize-names.csv`

| Former Name              | Current Name                  | Type  |
|--------------------------|-------------------------------|-------|
| IRR-Residential          | Accurity Valuation            | fka   |
| Top Dog Daycare          | Canine Campus                 | fka   |
| JJ's Candy Em            | Schwietert's Cones & Candy    | fka   |
| Sitters Etc.             | SEI Healthcare Services       | fka   |
| Lodie's Shaved Ice Shack | Summer Snow                   | fka   |
| Look Good Naked          | Trumi                         | fka   |
| Johnny Brusco's          | Johnny's New York Style Pizza | aka   |
| Conroy's                 | 1-800-Flowers.com             | alias |

## 2025-12-20

### New FRUNS assignments

Added 4 new internal FRUNS identifiers (FN25xxx series) for franchises not in FRANdata's database:

| ID | Brand | Franchisor | Notes |
|----------------|----------------|--------------------------|----------------|
| FN25001 | Creno's Pizza | Creno's Pizza Company | Ohio pizza chain, 23+ locations, franchising since 1987 |
| FN25002 | Gambino's Pizza | In The Sauce Brands, Inc. | Kansas pizza chain, actively franchising |
| FN25003 | Holy Cow | Holy Cow Franchise LLC | NYC halal burger franchise, est. 2018 |
| FN25004 | Green Mill On The Go | Green Mill Restaurants, LLC | Fast-casual spinoff of Green Mill, franchising since 2018 |
