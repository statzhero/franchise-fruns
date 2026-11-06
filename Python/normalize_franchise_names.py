"""Text normalization for franchise name matching.

Functions to clean and standardize franchise names before matching.

Sanitization pipeline:
1. Handle NA/encoding, lowercase
2. Transliterate accented chars to ASCII (café → cafe)
3. Replace @ with "at"
4. Remove apostrophes, commas, dots (joining letters)
5. Replace other non-alphanumeric with spaces
6. Remove stopwords and trailing suffixes (corp, franchise, org, geo)
7. Restore terms if result too short
8. Strip leading "the" only if result > min_chars (preserves short brand names)

All steps except 7 run as native polars string expressions (Rust regex).
"""

from __future__ import annotations

import re

import polars as pl

# Term patterns for removal ($ = trailing only, matched iteratively)
# Removal order: stopwords -> corp -> franchise -> org -> geo
# Restoration order: franchise -> org -> geo -> corp (skip stopwords)
TERM_PATTERNS = {
    "stopwords": r"\b(and|by|of)\b",
    "corp": r"\b(inc|incorporated|llc|ltd|limited|lp|co|corp|corporation|company|spv|spe)$",
    "franchise": r"\b(franchise|franchises|franchising|franchisor|license program|operator program)$",
    "org": r"\b(system|systems|holding|holdings|enterprise|enterprises)$",
    "geo": r"\b(us|usa|north america|intl|international)$",
}

# Skip stopwords in restoration (position matters, e.g., "The Tan" → "tan" not "tan the")
RESTORE_ORDER = ["franchise", "org", "geo", "corp"]


# Characters that NFD decomposition does not handle (ø → o, ß → ss, etc.)
# Matches R's stringi::stri_trans_general("Latin-ASCII") and Stata's ustrto(, "ascii", 2)
_TRANSLITERATE_MAP = {
    "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "ø": "o", "Ø": "O", "ß": "ss", "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L", "þ": "th", "Þ": "TH",
    "ð": "d", "Ð": "D",
}


def sanitize_name(x: str | pl.Series, min_chars: int = 4) -> str | pl.Series:
    """Normalize franchise name strings for matching.

    Args:
        x: A string or polars Series of strings to sanitize.
        min_chars: Minimum character length for result. Default is 4.

    Returns:
        Sanitized string(s) with normalized whitespace and removed suffixes.
    """
    if isinstance(x, pl.Series):
        return _sanitize_series(x, min_chars)
    return _sanitize_series(pl.Series([x]), min_chars).item()


def _sanitize_series(x: pl.Series, min_chars: int) -> pl.Series:
    """Sanitize a Series of names."""
    normalized = _squish(
        x.cast(pl.String)
        .fill_null("")
        .str.to_lowercase()
        # Remove special symbols before transliteration (® → (R) is unwanted)
        .str.replace_all(r"[®™©℠ªº°]", "")
        # Transliterate accented characters to ASCII (café → cafe, häagen → haagen):
        # first letters that NFD cannot decompose, then strip combining marks
        .str.replace_many(_TRANSLITERATE_MAP)
        .str.normalize("NFD")
        .str.replace_all(r"\p{Mn}", "")
        # Remove apostrophe variants and joining punctuation (no space left behind)
        .str.replace_all("@", "at", literal=True)
        .str.replace_all(r"['‘’‚‛ʼʹ`´,.]", "")
        # Other non-alphanumeric characters become spaces
        .str.replace_all(r"[^a-zA-Z0-9]", " ")
    )

    # Remove terms in order (trailing patterns run until no more matches)
    result = normalized
    for pattern in TERM_PATTERNS.values():
        while True:
            removed = _squish(result.str.replace_all(pattern, ""))
            if removed.equals(result):
                break
            result = removed

    # Restore terms if result too short but source was long enough. Few names
    # qualify, so these rows go through the per-string Python version.
    if min_chars > 0:
        too_short = (result.str.len_chars() < min_chars) & (
            normalized.str.len_chars() >= min_chars
        )
        idx = too_short.arg_true()
        if len(idx) > 0:
            restored = [
                _restore_until_min_chars(n, r, min_chars)
                for n, r in zip(
                    normalized.gather(idx), result.gather(idx), strict=True
                )
            ]
            result = result.scatter(idx, restored)

    # Strip leading "the " only if remaining result > min_chars
    # Preserves "the" for short names (e.g., "the now") but removes from longer ones
    s = pl.col("s")
    return (
        result.to_frame("s")
        .select(
            pl.when(s.str.starts_with("the ") & (s.str.len_chars() - 4 > min_chars))
            .then(s.str.slice(4))
            .otherwise(s)
        )
        .to_series()
        .alias(x.name)
    )


def _squish(x: pl.Series) -> pl.Series:
    """Collapse whitespace runs to a single space and trim both ends."""
    return x.str.replace_all(r"\s+", " ").str.strip_chars()


def _restore_until_min_chars(normalized: str, current: str, min_chars: int) -> str:
    """Restore removed terms until min_chars threshold is met."""
    for name in RESTORE_ORDER:
        if len(current) >= min_chars:
            break
        pattern = TERM_PATTERNS[name]
        # Replace $ anchor with \b - patterns are trailing-only for removal, but we
        # need to find whole-word terms anywhere in the string for restoration
        extract_pattern = re.sub(r"\$$", r"\\b", pattern)
        matched = re.findall(extract_pattern, normalized)
        for term in matched:
            if len(current) >= min_chars:
                break
            current = term if len(current) == 0 else f"{current} {term}"
        # Remove matched terms from normalized for next iteration
        normalized = re.sub(pattern, "", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip()
    return current


def harmonize_name(
    x: str | pl.Series, harmonize_map: pl.DataFrame
) -> str | pl.Series:
    """Apply harmonization mappings to sanitized names.

    Names mapped to NA in the harmonize file are intentional exclusions
    (e.g., "food", "plumber") -- they are mapped to empty string to block
    matching. Names not in the map are kept as-is.

    Args:
        x: A string or polars Series of sanitized names.
        harmonize_map: DataFrame with 'franchise' and 'name_harmonized' columns.

    Returns:
        Name(s) with harmonization mappings applied.
    """
    # Build lookup dict: NA mappings become "" (blocked), missing keys pass through
    lookup = dict(
        zip(
            harmonize_map["franchise"].to_list(),
            harmonize_map["name_harmonized"].fill_null("").to_list(),
            strict=True,
        )
    )
    # A null key would otherwise map null inputs, which must stay null
    lookup.pop(None, None)

    if isinstance(x, pl.Series):
        return x.replace(lookup)
    if x is None:
        return x
    return lookup.get(x, x)
