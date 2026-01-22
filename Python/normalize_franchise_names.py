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
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

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


def _transliterate_to_ascii(text: str) -> str:
    """Transliterate accented characters to ASCII (café → cafe)."""
    # Normalize to NFD (decompose accents), then remove combining marks
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def sanitize_name(x: str | pd.Series, min_chars: int = 4) -> str | pd.Series:
    """Normalize franchise name strings for matching.

    Args:
        x: A string or pandas Series of strings to sanitize.
        min_chars: Minimum character length for result. Default is 4.

    Returns:
        Sanitized string(s) with normalized whitespace and removed suffixes.
    """
    if isinstance(x, pd.Series):
        return x.apply(lambda val: _sanitize_single(val, min_chars))
    return _sanitize_single(x, min_chars)


def _sanitize_single(x: str | None, min_chars: int = 4) -> str:
    """Sanitize a single string value."""
    if x is None or pd.isna(x):
        return ""

    x = str(x)
    x = x.lower()

    # Remove special symbols before transliteration (® → (R) is unwanted)
    x = re.sub(r"[®™©℠ªº°]", "", x)

    # Transliterate accented characters to ASCII (café → cafe, häagen → haagen)
    x = _transliterate_to_ascii(x)

    # Remove apostrophe variants and joining punctuation (no space left behind)
    x = x.replace("@", "at")
    x = re.sub(r"['\u2018\u2019\u201A\u201B\u02BC\u02B9`\u00B4,.]", "", x)

    # Other non-alphanumeric characters become spaces
    x = re.sub(r"[^a-zA-Z0-9]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()

    normalized = x
    normalized_len = len(normalized)

    # Remove terms in order (trailing patterns run until no more matches)
    for pattern in TERM_PATTERNS.values():
        while True:
            new_x = re.sub(pattern, "", x).strip()
            new_x = re.sub(r"\s+", " ", new_x).strip()
            if new_x == x:
                break
            x = new_x

    # Restore terms if result too short but source was long enough
    if min_chars > 0 and len(x) < min_chars and normalized_len >= min_chars:
        x = _restore_until_min_chars(normalized, x, min_chars)

    # Strip leading "the " only if remaining result > min_chars
    # Preserves "the" for short names (e.g., "the now") but removes from longer ones
    if x.startswith("the "):
        without_the = x[4:]
        if len(without_the) > min_chars:
            x = without_the

    return x


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


def harmonize_name(x: str | pd.Series, harmonize_map: pd.DataFrame) -> str | pd.Series:
    """Apply harmonization mappings to sanitized names.

    Args:
        x: A string or pandas Series of sanitized names.
        harmonize_map: DataFrame with 'franchise' and 'name_harmonized' columns.

    Returns:
        Name(s) with harmonization mappings applied.
    """
    lookup = dict(zip(harmonize_map["franchise"], harmonize_map["name_harmonized"], strict=True))

    if isinstance(x, pd.Series):
        return x.map(lookup).fillna(x).where(x.notna(), x)
    return lookup.get(x, x) if x and not pd.isna(x) else x
