"""Shared fixtures for franchise-fruns tests."""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
RSCRIPT = "/usr/local/bin/Rscript"


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture
def fruns_data():
    return pd.read_csv(
        PROJECT_ROOT / "data" / "fruns-master.csv",
        dtype={
            "fruns": "str",
            "brand_name_sanitized": "str",
            "franchisor_sanitized": "str",
        },
    )


@pytest.fixture
def harmonize_map():
    return pd.read_csv(
        PROJECT_ROOT / "data" / "harmonize-names.csv",
        dtype={"franchise": "str", "name_harmonized": "str"},
    )


def run_r_script(code: str) -> str:
    """Run R code via Rscript and return stdout."""
    result = subprocess.run(
        [RSCRIPT, "--vanilla", "-e", code],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"R script failed:\n{result.stderr}")
    return result.stdout
