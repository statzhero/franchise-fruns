"""Regression cases for match_to_fruns from the 2026-11 FDD re-OCR name pilot.

Each case is an extracted franchise name whose FRUNS match was verified
against fruns-master.csv and the source FDD. Harmonize entries added or
corrected on 2026-11-12 cover most of them; a few test the sanitizer.
"""

import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "Python"))

from match_to_fruns import match_to_fruns

CASES = [
    # harmonize targets corrected
    ("Sweetwaters", "16725"),                     # was Sweets4Treats
    ("Jake's Wayback Burgers", "11932"),          # was Jake's (The Taco Maker)
    ("Jump!Zone", "12009"),                       # was JUMP ON IN
    ("Freshway", "11504"),                        # was Fresh&Co
    ("Growler USA", "15776"),                     # was The Growler Guys
    ("Apex Network", "10247"),                    # was Apex Leadership
    # FRUNS brand is a prefix of the trade name
    ("Jabz Boxing Fitness For Women", "16206"),
    ("Taco John's Restaurant", "13758"),
    ("Goodcents Deli Fresh", "12444"),
    # trade name is a prefix of the FRUNS brand
    ("OHM", "18679"),
    ("Handel's", "11708"),
    ("BGR", "10477"),
    ("Miss USA", "12383"),                        # "usa" is stripped as a geo term
    # same franchisor, different trade name
    ("ERA Group", "11318"),
    ("800-Carinsurance", "14485"),
    ("Villa Italian Kitchen", "14177"),
    ("Uno Chicago Grill", "14128"),
    ("KINGS ROAD COFFEE", "17287"),
    ("General Nutrition Centers", "11563"),
    ("AFC/American Family Care", "11136"),
    ("TWS TEMPORARY WALL SYSTEMS", "19099"),
    # fuzzy false positives redirected
    ("Honest1", "11805"),                         # was Honest (hospitality)
    ("Matto Espresso", "18790"),                  # was Mattress Depot
    ("Coles Bakery & Café", "18286"),             # was Michel's Bakery
    ("Rainbow Restoration", "13085"),             # was B.O.R. Restoration
    ("TA Express", "14583"),                      # was Thai Express
    ("ÖUMI SUSHI", "15602"),                      # was Yummi Sushi; Hissho brand
    # fuzzy false positives blocked (not in FRUNS)
    ("SUSHI BOX", None),                          # was SUSHI KYO
    ("CareDiem Home Care", None),                 # was CareMinders
    ("PickleRage", None),                         # was Picklr
    ("Soccer 5", None),                           # was Soccer6
    # sanitizer: ellipsis separates words
    ("The Joint...The Chiropractic Place", "13872"),
]


@pytest.mark.parametrize("name, expected", CASES)
def test_match_case(name, expected):
    result = match_to_fruns(pl.DataFrame({"franchise_name": [name]}), "franchise_name", verbose=False)
    assert result["fruns"][0] == expected
