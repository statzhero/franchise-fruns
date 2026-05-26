"""Shared fixtures for franchise-fruns tests."""

import subprocess
from pathlib import Path

import polars as pl
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
RSCRIPT = "/usr/local/bin/Rscript"


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture
def fruns_data():
    return pl.read_csv(
        PROJECT_ROOT / "data" / "fruns-master.csv",
        schema_overrides={
            "fruns": pl.Utf8,
            "brand_name_sanitized": pl.Utf8,
            "franchisor_sanitized": pl.Utf8,
        },
    )


@pytest.fixture
def harmonize_map():
    return pl.read_csv(
        PROJECT_ROOT / "data" / "harmonize-names.csv",
        schema_overrides={"franchise": pl.Utf8, "name_harmonized": pl.Utf8},
        null_values="NA",
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
