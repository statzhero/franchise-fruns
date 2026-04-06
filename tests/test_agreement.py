"""Cross-language agreement tests: Python vs R.

Runs the same inputs through both Python and R normalization functions
and asserts identical outputs.
"""

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "Python"))

from conftest import PROJECT_ROOT, RSCRIPT
from normalize_franchise_names import harmonize_name, sanitize_name

# Shared test inputs -- exercising each pipeline stage
SANITIZE_INPUTS = [
    "McDonald's Franchising, Inc.",
    "Subway",
    "7-Eleven",
    "Häagen-Dazs",
    "café",
    "",
    "Acme Corp",
    "Acme Franchising",
    "Acme International",
    "Chicken@Home",
    "The Great Franchise",
    "Brand™ Name®",
    "Doctor's Associates Inc.",
    "SOME UPPER CASE LLC",
    "Ørsted Energy",
    "naïve café résumé",
]

HARMONIZE_INPUTS = [
    "food",
    "plumber",
    "1800 flowers",
    "unknownfranchise123",
    "mcdonalds",
    "9round fitness",
]


def _python_sanitize(inputs: list[str]) -> list[str]:
    s = pd.Series(inputs)
    return list(sanitize_name(s))


def _run_r_with_json(inputs: list[str], r_code_template: str) -> list[str]:
    """Write inputs to a temp JSON file, run R code, read results from temp file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f_in:
        json.dump(inputs, f_in)
        in_path = f_in.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f_out:
        out_path = f_out.name

    code = r_code_template.format(in_path=in_path, out_path=out_path)
    result = subprocess.run(
        [RSCRIPT, "--vanilla", "-e", code],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"R script failed:\n{result.stderr}")

    with open(out_path) as f:
        return json.load(f)


def _r_sanitize(inputs: list[str]) -> list[str]:
    return _run_r_with_json(inputs, textwrap.dedent("""\
        source("R/normalize_franchise_names.R")
        inputs <- jsonlite::fromJSON("{in_path}")
        results <- sanitize_name(inputs)
        jsonlite::write_json(results, "{out_path}", auto_unbox = TRUE)
    """))


def _python_harmonize(inputs: list[str]) -> list[str]:
    hmap = pd.read_csv(
        Path(__file__).parent.parent / "data" / "harmonize-names.csv",
        dtype={"franchise": "str", "name_harmonized": "str"},
    )
    s = pd.Series(inputs)
    result = harmonize_name(s, hmap)
    # Normalize NA/NaN to "" for comparison
    return [v if pd.notna(v) and v != "" else "" for v in result]


def _r_harmonize(inputs: list[str]) -> list[str]:
    return _run_r_with_json(inputs, textwrap.dedent("""\
        source("R/normalize_franchise_names.R")
        h <- readr::read_csv("data/harmonize-names.csv", show_col_types = FALSE)
        inputs <- jsonlite::fromJSON("{in_path}")
        results <- harmonize_name(inputs, h)
        results[is.na(results)] <- ""
        jsonlite::write_json(results, "{out_path}", auto_unbox = TRUE)
    """))


class TestSanitizeAgreement:
    """sanitize_name should produce identical results in R and Python."""

    def test_sanitize_agreement(self):
        py_results = _python_sanitize(SANITIZE_INPUTS)
        r_results = _r_sanitize(SANITIZE_INPUTS)

        mismatches = []
        for inp, py, r in zip(SANITIZE_INPUTS, py_results, r_results):
            if py != r:
                mismatches.append(f"  {inp!r:40s} -> py={py!r:20s} r={r!r}")

        if mismatches:
            detail = "\n".join(mismatches)
            pytest.fail(f"sanitize_name disagreements:\n{detail}")


class TestHarmonizeAgreement:
    """harmonize_name should produce identical results in R and Python."""

    def test_harmonize_agreement(self):
        py_results = _python_harmonize(HARMONIZE_INPUTS)
        r_results = _r_harmonize(HARMONIZE_INPUTS)

        mismatches = []
        for inp, py, r in zip(HARMONIZE_INPUTS, py_results, r_results):
            if py != r:
                mismatches.append(f"  {inp!r:40s} -> py={py!r:20s} r={r!r}")

        if mismatches:
            detail = "\n".join(mismatches)
            pytest.fail(f"harmonize_name disagreements:\n{detail}")
