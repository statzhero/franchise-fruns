"""Tests for Python normalize_franchise_names."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "Python"))

from normalize_franchise_names import harmonize_name, sanitize_name


# -- sanitize_name -------------------------------------------------------------


@pytest.mark.parametrize(
    "input_name, expected",
    [
        ("McDonald's Franchising, Inc.", "mcdonalds"),
        ("Subway", "subway"),
        ("7-Eleven", "7 eleven"),
        ("Häagen-Dazs", "haagen dazs"),
        ("café", "cafe"),
        ("", ""),
        (None, ""),
        # Corporate suffixes removed
        ("Acme Corp", "acme"),
        ("Acme LLC", "acme"),
        ("Acme, Inc.", "acme"),
        # Franchise terms removed (trailing)
        ("Acme Franchising", "acme"),
        ("Acme Franchise", "acme"),
        # Geo terms removed (trailing)
        ("Acme International", "acme"),
        ("Acme USA", "acme"),
        # @ -> at
        ("Chicken@Home", "chickenathome"),
        # Leading "the" stripped when result > min_chars
        ("The Great Franchise", "great"),
        # Special symbols removed
        ("Brand™ Name®", "brand name"),
        # Transliteration of non-decomposable chars
        ("Ørsted", "orsted"),
        ("Straße", "strasse"),
    ],
)
def test_sanitize_name(input_name, expected):
    result = sanitize_name(input_name)
    assert result == expected


def test_sanitize_name_series():
    s = pd.Series(["McDonald's, Inc.", "Subway", None])
    result = sanitize_name(s)
    assert list(result) == ["mcdonalds", "subway", ""]


# -- harmonize_name ------------------------------------------------------------


def test_harmonize_blocks_na_entries(harmonize_map):
    """NA mappings in harmonize-names.csv should block matching (return "")."""
    test = pd.Series(["food", "plumber"])
    result = harmonize_name(test, harmonize_map)
    assert list(result) == ["", ""]


def test_harmonize_passes_through_unknown(harmonize_map):
    """Names not in the map should be returned as-is."""
    test = pd.Series(["unknownfranchise123"])
    result = harmonize_name(test, harmonize_map)
    assert list(result) == ["unknownfranchise123"]


def test_harmonize_maps_known_variants(harmonize_map):
    """Known variants should map to canonical names."""
    test = pd.Series(["1800 flowers"])
    result = harmonize_name(test, harmonize_map)
    assert list(result) == ["1 800 flowers"]
