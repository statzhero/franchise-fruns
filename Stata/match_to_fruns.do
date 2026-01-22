*! match_to_fruns.do - Match franchise names to FRUNS identifiers
*! Mirrors R/match_to_fruns.R and Python/match_to_fruns.py
*!
*! Main program:
*!   match_to_fruns - Full matching pipeline: sanitize, harmonize, exact + fuzzy
*!
*! Requirements:
*!   - Stata 17+ (frames, Unicode regex)
*!   - matchit from SSC (for fuzzy matching): ssc install matchit
*!   - normalize_franchise_names.do (sanitize_name, harmonize_name programs)
*!
*! Data files expected in data/ directory:
*!   - fruns-master.csv
*!   - harmonize-names.csv


version 17
set varabbrev off

// Load normalization programs from same directory as this script
// Try multiple locations: same directory, Stata/, stata/, or already loaded
capture program list sanitize_name
if _rc {
    local script_dir = subinstr(c(filename), "match_to_fruns.do", "", 1)
    capture do "`script_dir'normalize_franchise_names.do"
    if _rc {
        capture do "Stata/normalize_franchise_names.do"
        if _rc {
            capture do "stata/normalize_franchise_names.do"
            if _rc {
                display as error "normalize_franchise_names.do not found. Ensure it is in the same directory."
                exit 601
            }
        }
    }
}


capture program drop match_to_fruns
program define match_to_fruns
    *! Match franchise names to FRUNS identifiers
    *!
    *! Matches input names against FRUNS master file using:
    *!   1. Sanitization (normalize text)
    *!   2. Harmonization (apply manual mappings)
    *!   3. Exact matching on brand_name_sanitized
    *!   4. Exact matching on franchisor_sanitized (fallback)
    *!   5. Fuzzy matching via Jaro-Winkler (optional)
    *!
    *! Syntax:
    *!   match_to_fruns varname, ///
    *!       [FRUNSdata(string)] ///       // Path to fruns-master.csv
    *!       [HARMonize(string)] ///       // Path to harmonize-names.csv
    *!       [method(string)] ///          // exact|fuzzy|both (default: both)
    *!       [maxdist(real 0.10)] ///      // Max Jaro-Winkler distance for fuzzy
    *!       [quiet] ///                   // Suppress match summary (verbose by default)
    *!       [keep_details]                 // Keep diagnostic columns
    *!
    *! Creates variables:
    *!   fruns      - Matched FRUNS identifier
    *!   match_type - exact | franchisor | franchisor_multiple | fuzzy_XXXX | (missing)
    *!
    *! If keep_details option specified, also keeps:
    *!   name_sanitized  - Sanitized input name
    *!   name_harmonized - After harmonization
    *!   matched_brand   - Brand matched to (for fuzzy)
    *!   distance        - Jaro-Winkler distance (for fuzzy)
    *!
    *! Example:
    *!   use "mydata.dta", clear
    *!   match_to_fruns franchise_name, method(both)

    syntax varname(string), ///
        [FRUNSdata(string)] ///
        [HARMonize(string)] ///
        [method(string)] ///
        [maxdist(real 0.10)] ///
        [quiet] ///
        [keep_details]

    // Defaults
    if "`method'" == "" local method "both"
    if !inlist("`method'", "exact", "fuzzy", "both") {
        display as error "method() must be: exact, fuzzy, or both"
        exit 198
    }

    if "`frunsdata'" == "" local frunsdata "data/fruns-master.csv"
    if "`harmonize'" == "" local harmonize "data/harmonize-names.csv"

    // Check required files exist
    capture confirm file "`frunsdata'"
    if _rc {
        display as error "FRUNS data not found: `frunsdata'"
        exit 601
    }
    capture confirm file "`harmonize'"
    if _rc {
        display as error "Harmonize data not found: `harmonize'"
        exit 601
    }

    // Check matchit installed (needed for fuzzy)
    if inlist("`method'", "fuzzy", "both") {
        capture which matchit
        if _rc {
            display as error "matchit not installed. Run: ssc install matchit"
            exit 199
        }
    }

    quietly {
        // Store original row count
        local n_original = _N

        // Generate row ID for later joins
        gen long _row_id = _n

        // Step 1 & 2: Sanitize and harmonize
        sanitize_name `varlist', gen(_name_sanitized)
        harmonize_name _name_sanitized, gen(_name_harmonized) using("`harmonize'")

        // Load FRUNS data into frame
        frame create _fruns
        frame _fruns {
            import delimited "`frunsdata'", clear varnames(1) stringcols(_all)
            keep fruns brand_name_sanitized franchisor_sanitized
            // Ensure no missing in key columns
            drop if missing(brand_name_sanitized) | brand_name_sanitized == ""
        }

        // Initialize result variables
        gen str20 fruns = ""
        gen str20 match_type = ""
        if "`keep_details'" != "" {
            gen str100 _matched_brand = ""
            gen double _distance = .
        }
    }

    // Step 3a: Exact match on brand name
    quietly {
        frame _fruns: tempfile fruns_brand
        frame _fruns: save `fruns_brand'

        preserve
        keep _row_id _name_harmonized
        drop if missing(_name_harmonized) | _name_harmonized == ""
        rename _name_harmonized brand_name_sanitized
        merge m:1 brand_name_sanitized using `fruns_brand', ///
            assert(match master using) keep(match) nogenerate
        keep _row_id fruns
        rename fruns _fruns_exact
        tempfile exact_brand
        save `exact_brand'
        restore

        merge 1:1 _row_id using `exact_brand', assert(match master) nogenerate
        replace fruns = _fruns_exact if !missing(_fruns_exact)
        replace match_type = "exact" if !missing(_fruns_exact)
        capture drop _fruns_exact
    }

    // Step 3b: Exact match on franchisor (for unmatched)
    // Multiple brands may share a franchisor - handle explicitly
    quietly {
        frame _fruns {
            keep fruns franchisor_sanitized
            drop if missing(franchisor_sanitized) | franchisor_sanitized == ""
            rename franchisor_sanitized _franchisor_key
            // Do NOT deduplicate - we need to detect multiple matches
            tempfile fruns_franchisor
            save `fruns_franchisor'
        }

        preserve
        keep if missing(fruns)
        keep _row_id _name_harmonized
        drop if missing(_name_harmonized) | _name_harmonized == ""
        rename _name_harmonized _franchisor_key

        // Many-to-many merge to detect multiple matches
        joinby _franchisor_key using `fruns_franchisor', unmatched(master)

        // Count matches per input row
        bysort _row_id: gen _n_matches = _N

        // Single franchisor matches - unambiguous
        gen _fruns_single = fruns if _n_matches == 1
        gen _is_single = (_n_matches == 1)

        // Multiple franchisor matches - ambiguous
        gen _is_multiple = (_n_matches > 1 & !missing(fruns))

        // Keep one row per _row_id for merge back
        bysort _row_id (_n_matches): keep if _n == 1

        keep _row_id _fruns_single _is_single _is_multiple
        tempfile franchisor_matches
        save `franchisor_matches'
        restore

        merge 1:1 _row_id using `franchisor_matches', assert(match master) nogenerate

        // Single franchisor match
        replace fruns = _fruns_single if _is_single == 1 & !missing(_fruns_single)
        replace match_type = "franchisor" if _is_single == 1 & !missing(_fruns_single)

        // Multiple franchisor matches - flag as ambiguous, leave fruns empty
        replace match_type = "franchisor_multiple" if _is_multiple == 1

        capture drop _fruns_single _is_single _is_multiple
    }

    // Step 3c: Fuzzy matching (if method is fuzzy or both)
    if inlist("`method'", "fuzzy", "both") {
        quietly {
            // Get unmatched rows
            preserve
            if "`method'" == "both" {
                keep if missing(fruns)
            }
            keep _row_id _name_harmonized
            drop if missing(_name_harmonized) | _name_harmonized == ""

            if _N > 0 {
                // Prepare for matchit
                rename _name_harmonized txtraw
                gen idmaster = _row_id

                // Get unique brands from FRUNS (preserve for merge-back)
                frame _fruns {
                    keep fruns brand_name_sanitized
                    duplicates drop brand_name_sanitized, force
                    rename brand_name_sanitized txtraw
                    gen idusing = _n
                    tempfile fruns_for_match
                    save `fruns_for_match'
                }

                // Performance: compute similarity threshold from distance
                // matchit uses similarity (1 - distance), higher = better
                local sim_threshold = 1 - `maxdist'

                // Run fuzzy match with Jaro-Winkler
                // threshold() filters candidates early for performance
                local n_master = _N
                frame _fruns: local n_using = _N
                if `n_master' * `n_using' > 1000000 {
                    display as text "Note: Large fuzzy match (" ///
                        %10.0fc `n_master' " x " %10.0fc `n_using' ///
                        "). This may take a while."
                }

                matchit idmaster txtraw using `fruns_for_match', ///
                    idusing(idusing) txtusing(txtraw) similmethod(jw) ///
                    threshold(`sim_threshold')

                // Convert similarity to distance
                gen _distance = 1 - similscore

                // Keep best match per input row
                bysort idmaster (_distance): keep if _n == 1

                // Merge back to get FRUNS using idusing (reliable key)
                rename txtusing _matched_brand
                merge m:1 idusing using `fruns_for_match', ///
                    assert(match using) keep(match) nogenerate keepusing(fruns)

                // Prepare for merge back
                rename idmaster _row_id
                gen match_type = "fuzzy_" + string(_distance, "%6.4f")
                keep _row_id fruns match_type _matched_brand _distance
                tempfile fuzzy_matches
                save `fuzzy_matches'
            }
            restore

            // Merge fuzzy results back to main data
            capture confirm file `fuzzy_matches'
            if !_rc {
                merge 1:1 _row_id using `fuzzy_matches', ///
                    assert(match master) nogenerate update

                if "`keep_details'" != "" {
                    // Update detail columns from fuzzy match
                    capture replace _matched_brand = _matched_brand if match_type != ""
                    capture replace _distance = _distance if match_type != ""
                }
            }
        }
    }

    // Cleanup frames
    quietly frame drop _fruns

    // Handle keep_details option
    quietly {
        if "`keep_details'" != "" {
            rename _name_sanitized name_sanitized
            rename _name_harmonized name_harmonized
            rename _matched_brand matched_brand
            rename _distance distance
        }
        else {
            drop _name_sanitized _name_harmonized
            capture drop _matched_brand _distance
        }
        drop _row_id
    }

    // Verbose output
    if "`quiet'" == "" {
        display _n as text "{hline 40}"
        display as text "Match Summary"
        display as text "{hline 40}"

        quietly count
        local total = r(N)

        quietly count if !missing(fruns)
        local matched = r(N)
        local pct_matched = round(`matched' / `total' * 100, 0.1)

        display as text "Total rows:    " as result %10.0fc `total'
        display as text "Matched:       " as result %10.0fc `matched' " (" %4.1f `pct_matched' "%)"
        display ""

        // By match type (use levelsof for reliable string handling)
        quietly levelsof match_type if !missing(match_type), local(types)
        foreach t of local types {
            quietly count if match_type == "`t'"
            local this_n = r(N)
            local this_pct = round(`this_n' / `total' * 100, 0.1)
            display as text "  " %-12s "`t'" as result %8.0fc `this_n' "  " %5.1f `this_pct' "%"
        }

        quietly count if missing(fruns)
        local unmatched = r(N)
        local pct_unmatched = round(`unmatched' / `total' * 100, 0.1)
        display as text "  " %-12s "unmatched" as result %8.0fc `unmatched' "  " %5.1f `pct_unmatched' "%"

        display as text "{hline 40}"
    }
end
