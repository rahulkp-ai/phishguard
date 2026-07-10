"""
tests/test_integration_builder.py
===================================
Integration tests for ``phishguard.data.builder.build_dataset()``.

These tests write real URL files to a temp directory and call
``build_dataset()`` — no network access, no mocking.  They verify that:

- The output CSV has the right shape and column names.
- The ``label`` column contains only 0 and 1.
- Class balancing works correctly.
- Malformed URLs are skipped gracefully rather than crashing.
- The output CSV is actually written to disk.

Marked ``integration`` so CI can run them separately from fast unit tests::

    pytest -m integration
    pytest -m "not integration"   # unit tests only
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from phishguard.data.builder import build_dataset
from phishguard.features.extractor import FEATURE_NAMES, NUM_FEATURES

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PHISHING = [
    "http://192.168.1.1/login/verify-account",
    "http://paypal-account-suspended.xyz/restore",
    "http://secure-banking-update.com/account/verify/login",
    "http://paypal.account-verify.com/login",
    "http://amazon-security-alert.tk/verify",
    "http://bit.ly/abc123malware",
]

SAMPLE_LEGIT = [
    "https://google.com",
    "https://github.com",
    "https://stackoverflow.com",
    "https://python.org",
    "https://wikipedia.org",
    "https://linkedin.com",
]

MALFORMED_URLS = [
    "",
    "not_a_url",
    "   ",
    "://missing-scheme.com",
]


@pytest.fixture()
def url_files(tmp_path) -> tuple[Path, Path]:
    """Write sample URL files to a temp dir and return (phishing, legit) paths."""
    phish_path = tmp_path / "phishing.txt"
    legit_path = tmp_path / "legit.txt"
    phish_path.write_text("\n".join(SAMPLE_PHISHING) + "\n")
    legit_path.write_text("\n".join(SAMPLE_LEGIT) + "\n")
    return phish_path, legit_path


@pytest.fixture()
def mixed_url_files(tmp_path) -> tuple[Path, Path]:
    """URL files that include malformed entries."""
    phish_path = tmp_path / "phishing.txt"
    legit_path = tmp_path / "legit.txt"
    phish_path.write_text("\n".join(SAMPLE_PHISHING + MALFORMED_URLS) + "\n")
    legit_path.write_text("\n".join(SAMPLE_LEGIT) + "\n")
    return phish_path, legit_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildDatasetShape:
    def test_output_csv_is_created(self, url_files, tmp_path):
        phish, legit = url_files
        out = tmp_path / "dataset.csv"
        build_dataset(phish, legit, out)
        assert out.exists()

    def test_column_count(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv")
        # NUM_FEATURES feature columns + 1 label column
        assert df.shape[1] == NUM_FEATURES + 1

    def test_column_names(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv")
        assert list(df.columns) == FEATURE_NAMES + ["label"]

    def test_row_count_balanced(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv", balance=True)
        n = min(len(SAMPLE_PHISHING), len(SAMPLE_LEGIT))
        assert len(df) == n * 2

    def test_row_count_unbalanced(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv", balance=False)
        assert len(df) == len(SAMPLE_PHISHING) + len(SAMPLE_LEGIT)


class TestBuildDatasetLabels:
    def test_label_column_only_contains_0_and_1(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv")
        assert set(df["label"].unique()).issubset({0, 1})

    def test_balanced_dataset_has_equal_classes(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv", balance=True)
        counts = df["label"].value_counts()
        assert counts[0] == counts[1]

    def test_unbalanced_dataset_correct_label_counts(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv", balance=False)
        counts = df["label"].value_counts()
        assert counts[1] == len(SAMPLE_PHISHING)
        assert counts[0] == len(SAMPLE_LEGIT)


class TestBuildDatasetValues:
    def test_all_feature_values_in_unit_interval(self, url_files, tmp_path):
        phish, legit = url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv")
        feature_cols = df.drop("label", axis=1)
        assert (feature_cols >= 0.0).all().all()
        assert (feature_cols <= 1.0).all().all()

    def test_output_csv_readable_by_pandas(self, url_files, tmp_path):
        phish, legit = url_files
        out = tmp_path / "dataset.csv"
        build_dataset(phish, legit, out)
        df2 = pd.read_csv(out)
        assert list(df2.columns) == FEATURE_NAMES + ["label"]


class TestBuildDatasetRobustness:
    def test_malformed_urls_skipped_gracefully(self, mixed_url_files, tmp_path):
        """Malformed URLs must be skipped — build_dataset must not raise."""
        phish, legit = mixed_url_files
        df = build_dataset(phish, legit, tmp_path / "dataset.csv")
        # Should complete successfully — shape >= 1 row
        assert len(df) >= 1

    def test_output_dir_created_if_missing(self, url_files, tmp_path):
        phish, legit = url_files
        out = tmp_path / "nested" / "deep" / "dataset.csv"
        build_dataset(phish, legit, out)
        assert out.exists()
