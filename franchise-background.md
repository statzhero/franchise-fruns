# Franchise Disclosure Documents and FRUNS

This document explains why matching franchise names to unique identifiers is harder than it looks. Brand, franchise, and franchisor names typically come from Franchise Disclosure Documents (FDDs), often via scans, which creates messy variants requiring normalization. [Atz (2025)](https://doi.org/10.2139/ssrn.5381656) provides additional background on the US franchise market.

## Franchise Disclosure Documents (FDDs)

FTC Rule 436 requires franchisors selling in the United States to provide prospective buyers with a Franchise Disclosure Document at least 14 days before signing. The FDD follows a standardized 23-item structure covering franchise history, fees, obligations, and operational details. All items are mandatory except Item 19 (Financial Performance Representations), which remains voluntary. Four states (California, Minnesota, Wisconsin, and Indiana) publish FDDs through public commerce portals.

## FRUNS: The Franchise Unique Numbering System

FRUNS is a proprietary identifier for franchise systems maintained by FRANdata through the [Franchise Registry](https://www.franchiseregistry.com/fruns/). Each franchise brand receives a unique code regardless of corporate restructuring or name changes. Since 2013, the Small Business Administration has required a FRUNS for all franchise loans, making it the de facto standard identifier. FRUNS also links current brand names to predecessors through mergers, acquisitions, and rebranding. According to FRANdata, new FRUNS are issued only after reviewing a valid FDD or equivalent documentation.

## Name Variation Examples

Franchise names extracted from FDDs vary for several reasons, all of which complicate matching.

**Corporate suffixes** appear inconsistently: "Subway" may appear as "Subway, Inc.", "Subway LLC", "Subway Franchising LLC", or "Doctor's Associates Inc." (its actual franchisor name).

**Geographic markers** distinguish regional entities: "Dunkin' Donuts of California", "Pizza Hut North America", "7-Eleven International LLC".

**Multiple brand variants** appear with slashes: "Chevys/Chevys Fresh Mex/Fresh Mex", "Bikram's Yoga College/Bikram Yoga", "Checkers/Rally's".

**Brand vs. franchisor mismatch**: The legal entity often differs from the consumer-facing brand. "MTY Franchising USA, Inc." operates Cold Stone Creamery; "Roark Capital" owns multiple franchise brands under different legal names.

**Name evolution** occurs through rebranding ("Dunkin' Donuts" → "Dunkin'") or mergers.

## Franchises Missing from FRUNS

FRUNS coverage depends on franchises actively submitting documentation. Several categories may be absent or hard to match:

-   **New franchises** in their first year may not yet have a FRUNS.
-   **Mergers and acquisitions** create new entities.
-   **Franchises not seeking SBA loans** face less pressure to register.
-   **Non-registration states** are less visible unless they approach FRANdata directly.
-   **Small or regional systems** with limited growth ambitions may never pursue registration.

## Internal Identifier Scheme

For franchises missing from FRUNS, this project assigns internal identifiers using an `FN` prefix + 2-digit year + sequence number (e.g., `FN25001`). Official FRUNS retain their numeric IDs. See `NEWS.md` for a log of additions.