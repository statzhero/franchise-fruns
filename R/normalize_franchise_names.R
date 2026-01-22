#' Text normalization for franchise name matching
#'
#' Functions to clean and standardize franchise names before matching.
#'
#' Sanitization pipeline:
#' 1. Handle NA/encoding, lowercase
#' 2. Transliterate accented chars to ASCII (café → cafe)
#' 3. Replace @ with "at"
#' 4. Remove apostrophes, commas, dots (joining letters)
#' 5. Replace other non-alphanumeric with spaces
#' 6. Remove stopwords and trailing suffixes (corp, franchise, org, geo)
#' 7. Restore terms if result too short
#' 8. Strip leading "the" only if result > min_chars (preserves short brand names)

# Term patterns for removal ($ = trailing only, matched iteratively)
# Removal order: stopwords -> corp -> franchise -> org -> geo
# Restoration order: franchise -> org -> geo -> corp (skip stopwords)
TERM_PATTERNS <- list(
  stopwords = "\\b(and|by|of)\\b",
  corp = "\\b(inc|incorporated|llc|ltd|limited|lp|co|corp|corporation|company|spv|spe)$",
  franchise = "\\b(franchise|franchises|franchising|franchisor|license program|operator program)$",
  org = "\\b(system|systems|holding|holdings|enterprise|enterprises)$",
  geo = "\\b(us|usa|north america|intl|international)$"
)

# Sanitization -----------------------------------------------------------------

# Normalize franchise name strings for matching
sanitize_name <- function(x, min_chars = 4) {
  x <- dplyr::if_else(is.na(x), "", x)
  x <- iconv(x, from = "UTF-8", to = "UTF-8", sub = "")
  x <- tolower(x)

  # Remove special symbols before transliteration (® → (R) is unwanted)
  x <- stringr::str_remove_all(x, "[®™©℠ªº°]")

  # Transliterate accented characters to ASCII (café → cafe, häagen → haagen)
  x <- stringi::stri_trans_general(x, "Latin-ASCII")

  # Remove apostrophe variants and joining punctuation (no space left behind)
  x <- stringr::str_replace_all(x, "@", "at")
  x <- stringr::str_remove_all(x, "['\u2018\u2019\u201A\u201B\u02BC\u02B9`\u00B4,.]")

  # Other non-alphanumeric characters become spaces
  x <- stringr::str_replace_all(x, "[^[:alnum:]]", " ")
  x <- stringr::str_squish(x)

  normalized <- x

  # Remove terms in order (trailing patterns run until no more matches)
  for (name in names(TERM_PATTERNS)) {
    pattern <- TERM_PATTERNS[[name]]
    repeat {
      new_x <- stringr::str_remove_all(x, pattern)
      new_x <- stringr::str_squish(new_x)
      if (identical(new_x, x)) {
        break
      }
      x <- new_x
    }
  }

  # Restore terms if result too short but source was long enough
  needs_restore <- nchar(x) < min_chars & nchar(normalized) >= min_chars
  needs_restore <- dplyr::if_else(is.na(needs_restore), FALSE, needs_restore)
  if (any(needs_restore)) {
    x[needs_restore] <- purrr::map2_chr(
      normalized[needs_restore],
      x[needs_restore],
      \(norm, short) restore_until_min_chars(norm, short, min_chars)
    )
  }

  # Strip leading "the " only if remaining result > min_chars
  # Preserves "the" for short names (e.g., "the now") but removes from longer ones
  starts_the <- stringr::str_starts(x, "the ")
  without_the <- stringr::str_remove(x, "^the ")
  x <- dplyr::if_else(
    starts_the & nchar(without_the) > min_chars,
    without_the,
    x
  )

  x
}

restore_until_min_chars <- function(normalized, current, min_chars) {
  # Restore in different order: skip stopwords (position matters), corp last
  restore_order <- c("franchise", "org", "geo", "corp")
  for (name in restore_order) {
    if (nchar(current) >= min_chars) {
      break
    }
    pattern <- TERM_PATTERNS[[name]]
    # Replace $ anchor with \b - patterns are trailing-only for removal, but we
    # need to find whole-word terms anywhere in the string for restoration
    extract_pattern <- stringr::str_replace(pattern, "\\$$", "\\\\b")
    matched <- stringr::str_extract_all(normalized, extract_pattern)[[1]]
    for (term in matched) {
      if (nchar(current) >= min_chars) {
        break
      }
      current <- if (nchar(current) == 0) term else paste(current, term)
    }
    # Remove matched terms from normalized for next iteration
    normalized <- stringr::str_remove_all(normalized, pattern)
    normalized <- stringr::str_squish(normalized)
  }
  current
}

# Harmonization ----------------------------------------------------------------

#' Apply harmonization mappings to sanitized names
harmonize_name <- function(x, harmonize_map) {
  lookup <- stats::setNames(
    harmonize_map$name_harmonized,
    harmonize_map$franchise
  )
  dplyr::coalesce(lookup[x], x)
}
