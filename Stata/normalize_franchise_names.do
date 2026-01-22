*! normalize_franchise_names.do - Text normalization for franchise name matching
*! Mirrors R/normalize_franchise_names.R and Python/normalize_franchise_names.py
*!
*! Sanitization pipeline:
*!   1. Handle NA/encoding, lowercase
*!   2. Transliterate accented chars to ASCII (café → cafe)
*!   3. Replace @ with "at"
*!   4. Remove apostrophes, commas, dots (joining letters)
*!   5. Replace other non-alphanumeric with spaces
*!   6. Remove stopwords and trailing suffixes (corp, franchise, org, geo)
*!   7. Restore terms if result too short
*!   8. Strip leading "the" only if result > min_chars (preserves short brand names)
*!
*! Programs:
*!   sanitize_name  - Normalize franchise name strings for matching
*!   harmonize_name - Apply harmonization mappings using frames

version 17
set varabbrev off

capture program drop sanitize_name
program define sanitize_name
    *! Normalize franchise name strings for matching
    *!
    *! Removal order: stopwords -> corp -> franchise -> org -> geo
    *! Restoration order: franchise -> org -> geo -> corp (skip stopwords)
    *!
    *! Syntax: sanitize_name inputvar, generate(newvar) [minchars(#)]
    *!
    *! Example:
    *!   sanitize_name franchise_name, gen(name_sanitized)
    *!   // "McDonald's Franchising, Inc." -> "mcdonalds"

    syntax varname(string), GENerate(name) [MINchars(integer 4)]

    confirm new variable `generate'

    quietly {
        gen `generate' = `varlist'
        replace `generate' = "" if missing(`generate')
        replace `generate' = strlower(`generate')

        // Remove special symbols before transliteration (® → (R) is unwanted)
        replace `generate' = ustrregexra(`generate', "[®™©℠ªº°]", "")

        // Transliterate accented characters to ASCII (café → cafe)
        replace `generate' = ustrto(`generate', "ascii", 2)

        // Character substitutions (join across, no space added)
        replace `generate' = subinstr(`generate', "@", "at", .)
        replace `generate' = ustrregexra(`generate', "['\u2018\u2019\u201A\u201B\u02BC\u02B9`\u00B4,.]", "")

        // Other non-alphanumeric characters become spaces
        replace `generate' = ustrregexra(`generate', "[^a-zA-Z0-9 ]", " ")
        replace `generate' = strtrim(stritrim(`generate'))

        // Save normalized for restoration
        tempvar normalized
        gen `normalized' = `generate'

        // 1. Stopwords (anywhere) - "the" handled separately at end (step 8)
        //    to preserve short brand names like "the now"
        replace `generate' = " " + `generate' + " "
        foreach word in and by of {
            replace `generate' = subinstr(`generate', " `word' ", " ", .)
        }
        replace `generate' = strtrim(stritrim(`generate'))

        // 2. Corporate suffixes (trailing only) - loop until no change
        local changed = 1
        while `changed' {
            tempvar before
            gen `before' = `generate'
            foreach suffix in inc incorporated llc ltd limited lp co corp corporation company spv spe {
                replace `generate' = ustrregexra(`generate', " `suffix'$", "")
                replace `generate' = ustrregexra(`generate', "^`suffix'$", "")
            }
            replace `generate' = strtrim(`generate')
            count if `before' != `generate'
            local changed = r(N)
            drop `before'
        }

        // 3. Franchise terms (trailing only) - loop until no change
        local changed = 1
        while `changed' {
            tempvar before
            gen `before' = `generate'
            foreach term in franchise franchises franchising franchisor {
                replace `generate' = ustrregexra(`generate', " `term'$", "")
                replace `generate' = ustrregexra(`generate', "^`term'$", "")
            }
            replace `generate' = ustrregexra(`generate', " license program$", "")
            replace `generate' = ustrregexra(`generate', " operator program$", "")
            replace `generate' = strtrim(`generate')
            count if `before' != `generate'
            local changed = r(N)
            drop `before'
        }

        // 4. Org terms (trailing only) - loop until no change
        local changed = 1
        while `changed' {
            tempvar before
            gen `before' = `generate'
            foreach term in system systems holding holdings enterprise enterprises {
                replace `generate' = ustrregexra(`generate', " `term'$", "")
            }
            replace `generate' = strtrim(`generate')
            count if `before' != `generate'
            local changed = r(N)
            drop `before'
        }

        // 5. Geo terms (trailing) - loop until no change
        local changed = 1
        while `changed' {
            tempvar before
            gen `before' = `generate'
            foreach term in us usa intl international {
                replace `generate' = ustrregexra(`generate', " `term'$", "")
            }
            replace `generate' = ustrregexra(`generate', " north america$", "")
            replace `generate' = strtrim(`generate')
            count if `before' != `generate'
            local changed = r(N)
            drop `before'
        }

        // Restoration if result too short but source was long enough
        // Order: franchise -> org -> geo -> corp (skip stopwords)
        // Match whole words anywhere (not just trailing) using \b word boundaries
        if `minchars' > 0 {
            // Franchise terms
            foreach term in franchise franchises franchising franchisor {
                replace `generate' = `generate' + " `term'" ///
                    if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                    & ustrregexm(`normalized', "\b`term'\b")
            }
            // Org terms
            foreach term in system systems holding holdings enterprise enterprises {
                replace `generate' = `generate' + " `term'" ///
                    if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                    & ustrregexm(`normalized', "\b`term'\b")
            }
            // Geo terms (order longer before shorter to prefer "usa" over "us")
            replace `generate' = `generate' + " north america" ///
                if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                & ustrregexm(`normalized', "\bnorth america\b")
            replace `generate' = `generate' + " international" ///
                if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                & ustrregexm(`normalized', "\binternational\b")
            replace `generate' = `generate' + " intl" ///
                if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                & ustrregexm(`normalized', "\bintl\b")
            replace `generate' = `generate' + " usa" ///
                if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                & ustrregexm(`normalized', "\busa\b")
            replace `generate' = `generate' + " us" ///
                if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                & ustrregexm(`normalized', "\bus\b")
            // Corp suffixes (restored last)
            foreach suffix in inc incorporated llc ltd limited lp co corp corporation company spv spe {
                replace `generate' = `generate' + " `suffix'" ///
                    if strlen(`generate') < `minchars' & strlen(`normalized') >= `minchars' ///
                    & ustrregexm(`normalized', "\b`suffix'\b")
            }
            replace `generate' = strtrim(`generate')
        }

        // Strip leading "the " only if remaining result > min_chars
        // Preserves "the" for short names (e.g., "the now") but removes from longer ones
        tempvar without_the
        gen `without_the' = ustrregexra(`generate', "^the ", "")
        replace `generate' = `without_the' if ustrregexm(`generate', "^the ") & strlen(`without_the') > `minchars'
        drop `without_the'

        drop `normalized'
    }
end


capture program drop harmonize_name
program define harmonize_name
    *! Apply harmonization mappings to sanitized names
    *!
    *! Looks up sanitized name in harmonize file. If found, replaces with
    *! canonical name. Empty mappings block generic terms from matching.
    *!
    *! Syntax: harmonize_name inputvar, generate(newvar) using(harmonize_file)
    *!
    *! Uses Stata frames for efficient multi-dataset handling.
    *! See: https://www.stata.com/manuals/dframesintro.pdf
    *!
    *! Example:
    *!   harmonize_name name_sanitized, gen(name_harmonized) using("data/harmonize-names.csv")

    syntax varname(string), GENerate(name) Using(string)

    confirm new variable `generate'

    // Store current frame name
    local current_frame = c(frame)

    quietly {
        // Load harmonize map into separate frame
        frame create _harmonize_temp
        frame _harmonize_temp {
            import delimited `using', clear varnames(1) stringcols(_all)
            keep franchise name_harmonized
            rename franchise _h_key
            rename name_harmonized _h_value
        }

        // Create merge key in current frame
        gen _h_key = `varlist'

        // Merge using frlink/frget (modern frame-based approach)
        frlink m:1 _h_key, frame(_harmonize_temp)
        frget _h_value, from(_harmonize_temp)

        // Apply harmonization logic:
        // - Matched with non-empty value: use harmonized name
        // - Matched with empty value: keep empty (blocks matching)
        // - Not matched: keep original sanitized name
        gen `generate' = cond(!missing(_harmonize_temp) & _h_value != "", _h_value, ///
                              cond(!missing(_harmonize_temp) & _h_value == "", "", `varlist'))

        // Cleanup
        drop _h_key _h_value _harmonize_temp
        frame drop _harmonize_temp
    }
end
