#' Match franchise names to FRUNS identifiers
#'
#' Matches input franchise names against the FRUNS master file using
#' sanitization, harmonization, and optional fuzzy matching.
#'
#' @param data Data frame containing franchise names to match
#' @param name_col Column containing franchise names (unquoted)
#' @param method Matching method:
#'   - "exact": exact matching only (fast, no false positives)
#'   - "fuzzy": fuzzy matching only (for testing/diagnostics)
#'   - "both": exact first, then fuzzy for unmatched (recommended)
#' @param fruns_data FRUNS lookup table (defaults to package data)
#' @param harmonize_map Harmonization mappings (defaults to package data)
#' @param max_distance Maximum Jaro-Winkler distance for fuzzy matches (default 0.10)
#' @param verbose Print match summary and sample fuzzy matches (default TRUE)
#' @param keep_details Keep diagnostic columns: name_sanitized, name_harmonized, distance (default FALSE)
#' @return Input data with `fruns` and `match_type` columns added

source("R/normalize_franchise_names.R")

# Data loading -----------------------------------------------------------------

load_fruns_data <- function() {
  readr::read_csv("data/fruns-master.csv", show_col_types = FALSE)
}

load_harmonize_map <- function() {
  # Keep NA mappings - they're intentional exclusions for generic names
  # (e.g., "pizza", "plumber") that would otherwise cause false positives.
  readr::read_csv("data/harmonize-names.csv", show_col_types = FALSE)
}

# Main function ----------------------------------------------------------------

match_to_fruns <- function(
  data,
  name_col,
  method = c("both", "exact", "fuzzy"),
  fruns_data = NULL,
  harmonize_map = NULL,
  max_distance = 0.10,
  verbose = TRUE,
  keep_details = FALSE
) {
  method <- match.arg(method)

  fruns_data <- fruns_data %||% load_fruns_data()
  harmonize_map <- harmonize_map %||% load_harmonize_map()

  prepared <- prepare_input(data, {{ name_col }}, harmonize_map)

  if (method == "exact") {
    exact_matches <- find_exact_matches(prepared, fruns_data)
    result <- finalize_matches(prepared, exact_matches, keep_details)
    if (verbose) {
      print_summary(result)
    }
    return(result)
  }

  if (method == "fuzzy") {
    fuzzy_matches <- match_fuzzy(prepared, fruns_data, max_distance)
    result <- finalize_matches(prepared, fuzzy_matches, keep_details)
    if (verbose) {
      print_summary(result, fuzzy_matches)
    }
    return(result)
  }

  # method == "both": exact first, then fuzzy for unmatched
  exact_matches <- find_exact_matches(prepared, fruns_data)

  unmatched <- prepared |>
    dplyr::anti_join(exact_matches, by = dplyr::join_by(.row_id))

  if (nrow(unmatched) == 0) {
    fuzzy_matches <- dplyr::tibble()
  } else {
    fuzzy_matches <- match_fuzzy(unmatched, fruns_data, max_distance)
  }

  all_matches <- dplyr::bind_rows(exact_matches, fuzzy_matches)
  result <- finalize_matches(prepared, all_matches, keep_details)
  if (verbose) {
    print_summary(result, fuzzy_matches)
  }
  result
}

# Step 1: Sanitization ---------------------------------------------------------
# Clean up input names: lowercase, replace @ with "at", remove apostrophes/dots,
# strip corporate suffixes (Inc, LLC, Corp), franchise terms (Franchise,
# Franchising, Franchisor), and trailing terms (International, Holdings, USA).
# Example: "McDonald's Franchising, Inc." → "mcdonalds"

# Step 2: Harmonization --------------------------------------------------------
# Apply manual mapping from harmonize-names.csv. Maps known variants to
# canonical names (e.g., "mcd" → "mcdonalds"). NA mappings intentionally block
# generic terms from matching (e.g., "food" → NA prevents false positives).

# Step 3: Matching -------------------------------------------------------------
# Find the FRUNS ID using the harmonized name:
#   - Exact (brand): match against brand_name_sanitized in FRUNS master
#   - Exact (franchisor): if no brand match, try franchisor_sanitized
#   - Fuzzy: if still unmatched, find closest brand via Jaro-Winkler (≤0.10)

# Helpers ----------------------------------------------------------------------

prepare_input <- function(data, name_col, harmonize_map) {
  data |>
    dplyr::mutate(
      .row_id = dplyr::row_number(),
      .name_sanitized = sanitize_name({{ name_col }}),
      .name_harmonized = harmonize_name(.name_sanitized, harmonize_map)
    )
}

find_exact_matches <- function(data, fruns_data) {
  # Step 3a: Exact match on brand name
  # Brand names should be unique in FRUNS - error if multiple matches found
  exact_brand <- data |>
    dplyr::inner_join(
      fruns_data |> dplyr::select(fruns, brand_name_sanitized),
      by = dplyr::join_by(.name_harmonized == brand_name_sanitized),
      na_matches = "never",
      relationship = "many-to-one"
    ) |>
    dplyr::mutate(match_type = "exact")

  # Step 3b: Exact match on franchisor name (for rows not matched by brand)
  # Multiple franchises may share a franchisor name - handle explicitly
  unmatched_by_brand <- data |>
    dplyr::anti_join(exact_brand, by = dplyr::join_by(.row_id))

  franchisor_joined <- unmatched_by_brand |>
    dplyr::inner_join(
      fruns_data |> dplyr::select(fruns, franchisor_sanitized),
      by = dplyr::join_by(.name_harmonized == franchisor_sanitized),
      na_matches = "never",
      relationship = "many-to-many"
    ) |>
    dplyr::mutate(
      .n_matches = dplyr::n(),
      .by = .row_id
    )

  # Single franchisor matches
  exact_franchisor <- franchisor_joined |>
    dplyr::filter(.n_matches == 1) |>
    dplyr::select(-.n_matches) |>
    dplyr::mutate(match_type = "franchisor")

  # Multiple franchisor matches - ambiguous, cannot determine correct FRUNS
  franchisor_multiple <- franchisor_joined |>
    dplyr::filter(.n_matches > 1) |>
    dplyr::distinct(.row_id, .keep_all = TRUE) |>
    dplyr::mutate(
      fruns = NA_character_,
      match_type = "franchisor_multiple"
    ) |>
    dplyr::select(-.n_matches)

  dplyr::bind_rows(exact_brand, exact_franchisor, franchisor_multiple)
}

finalize_matches <- function(prepared, matches, keep_details = FALSE) {
  if (keep_details) {
    keep_cols <- c(
      ".row_id",
      "fruns",
      "match_type",
      ".matched_brand",
      ".distance"
    )
    matches <- matches |>
      dplyr::select(dplyr::any_of(keep_cols))

    prepared |>
      dplyr::left_join(matches, by = dplyr::join_by(.row_id)) |>
      dplyr::rename_with(
        \(x) stringr::str_remove(x, "^\\."),
        dplyr::starts_with(".")
      )
  } else {
    matches <- matches |>
      dplyr::select(.row_id, fruns, match_type)

    prepared |>
      dplyr::left_join(matches, by = dplyr::join_by(.row_id)) |>
      dplyr::select(-dplyr::starts_with("."))
  }
}

print_summary <- function(result, fuzzy_matches = NULL) {
  counts <- result |>
    dplyr::mutate(
      match_bucket = dplyr::case_when(
        is.na(match_type) ~ "unmatched",
        startsWith(match_type, "fuzzy") ~ "fuzzy",
        .default = match_type
      )
    ) |>
    dplyr::count(match_bucket) |>
    dplyr::mutate(pct = n / sum(n) * 100)

  total <- nrow(result)
  matched <- sum(counts$n[counts$match_bucket != "unmatched"])

  cli::cli_h2("Match Summary")
  cli::cli_text(
    "{.strong {total}} rows \u2192 {.strong {matched}} matched ({round(matched/total*100, 1)}%)"
  )

  # Tabular summary
  max_type <- max(nchar(counts$match_bucket))
  fmt <- paste0("  %-", max_type, "s  %6d  %5.1f%%")
  cli::cli_verbatim("")
  cli::cli_verbatim(sprintf(fmt, counts$match_bucket, counts$n, counts$pct))

  if (!is.null(fuzzy_matches) && nrow(fuzzy_matches) > 0) {
    samples <- fuzzy_matches |>
      dplyr::slice_sample(n = min(10, nrow(fuzzy_matches))) |>
      dplyr::arrange(.distance)

    cli::cli_h2("Fuzzy Match Samples")
    cli::cli_verbatim(sprintf(
      "  %-30.30s  \u2192  %-30.30s  %.3f",
      samples$.name_harmonized,
      samples$.matched_brand,
      samples$.distance
    ))
  }

  invisible(result)
}

# Step 3c: Fuzzy matching ------------------------------------------------------

#' Find best fuzzy match for each unmatched name via Jaro-Winkler (≤0.10)
match_fuzzy <- function(data, fruns_data, max_distance) {
  unique_input <- unique(data$.name_harmonized)
  unique_brands <- unique(fruns_data$brand_name_sanitized)

  # Find best match index directly (no full matrix needed)
  best_idx <- stringdist::amatch(
    unique_input,
    unique_brands,
    method = "jw",
    p = 0.1,
    maxDist = max_distance
  )

  has_match <- !is.na(best_idx)
  if (!any(has_match)) {
    return(dplyr::tibble())
  }

  # Build matches for inputs that found something
  best_matches <- dplyr::tibble(
    .name_harmonized = unique_input[has_match],
    .matched_brand = unique_brands[best_idx[has_match]]
  ) |>
    dplyr::mutate(
      .distance = stringdist::stringdist(
        .name_harmonized,
        .matched_brand,
        method = "jw",
        p = 0.1
      )
    )

  # Join to get FRUNS and back to original data
  best_matches |>
    dplyr::left_join(
      fruns_data |> dplyr::distinct(brand_name_sanitized, fruns),
      by = dplyr::join_by(.matched_brand == brand_name_sanitized)
    ) |>
    dplyr::inner_join(data, by = dplyr::join_by(.name_harmonized)) |>
    dplyr::mutate(match_type = paste0("fuzzy_", round(.distance, 4)))
}
