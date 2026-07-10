"""
tests/test_features.py
======================
Unit tests for phishguard.features.extractor.

Run: pytest tests/test_features.py -v
"""

from __future__ import annotations

import pytest

from phishguard.features.extractor import (
    FEATURE_NAMES,
    NUM_FEATURES,
    extract_features,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def features_dict(url: str) -> dict[str, float]:
    return dict(zip(FEATURE_NAMES, extract_features(url)))


def phishing_score(url: str) -> float:
    return sum(extract_features(url))


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_feature_count():
    """extract_features must return exactly NUM_FEATURES values."""
    assert len(extract_features("https://google.com")) == NUM_FEATURES


def test_feature_count_is_28():
    """Regression: duplicate f30 was removed; count must be 28 not 30."""
    assert NUM_FEATURES == 28


def test_feature_names_length():
    """FEATURE_NAMES list must match NUM_FEATURES."""
    assert len(FEATURE_NAMES) == NUM_FEATURES


def test_feature_names_unique():
    """Every feature name must be distinct — no duplicates."""
    assert len(set(FEATURE_NAMES)) == NUM_FEATURES


def test_all_values_in_unit_interval():
    """All feature values must be in [0, 1]."""
    urls = [
        "https://google.com",
        "http://192.168.1.1/login",
        "http://paypal-secure.tk/verify/account/login",
    ]
    for url in urls:
        for val in extract_features(url):
            assert 0.0 <= val <= 1.0, f"Out-of-range value {val} for {url}"


# ---------------------------------------------------------------------------
# Known-legitimate sites — low phishing score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com",
        "https://chatgpt.com/c/69abaa4b-7674-8323-b419-37dedc7d6382",
        "https://gemini.google.com/app/d03204b65cebf39f",
        "https://youtube.com/shorts/9a_7EuJOBfg?si=w1AMtyXuq_2OrZf2",
        "https://www.coursera.org/learn/python-project/home/module/1",
        "https://github.com/user/repo/blob/main/README.md",
    ],
)
def test_legit_urls_low_score(url):
    score = phishing_score(url)
    assert score <= 2.0, f"Legit URL scored too high ({score:.2f}): {url}"


# ---------------------------------------------------------------------------
# Known-phishing URLs — high phishing score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1/login/verify-account",
        "http://paypal-account-suspended.xyz/restore",
        "http://secure-banking-update.com/account/verify/login/confirm/password/reset",
        "http://paypal.account-verify.com/login",
        "http://amazon-security-alert.tk/verify",
    ],
)
def test_phishing_urls_high_score(url):
    score = phishing_score(url)
    assert score >= 2.0, f"Phishing URL scored too low ({score:.2f}): {url}"


# ---------------------------------------------------------------------------
# Individual feature correctness
# ---------------------------------------------------------------------------


def test_has_ip_detected():
    f = features_dict("http://192.168.1.1/login")
    assert f["has_ip"] == 1.0


def test_has_ip_absent():
    f = features_dict("https://google.com")
    assert f["has_ip"] == 0.0


def test_shortener_detected():
    f = features_dict("http://bit.ly/abc123")
    assert f["has_shortener"] == 1.0


def test_at_symbol_detected():
    f = features_dict("http://example.com@evil.com/path")
    assert f["has_at_symbol"] == 1.0


def test_at_symbol_absent():
    f = features_dict("https://github.com/user/repo")
    assert f["has_at_symbol"] == 0.0


def test_suspicious_tld_detected():
    f = features_dict("http://fakesite.tk/login")
    assert f["suspicious_tld"] == 1.0


def test_brand_in_subdomain_detected():
    f = features_dict("http://paypal.evil-site.com/login")
    assert f["brand_in_subdomain"] == 1.0


def test_encoded_chars_in_domain():
    f = features_dict("http://g%6Fgle.com/search")
    assert f["encoded_chars"] == 1.0


def test_https_in_domain_text():
    # Phishers put "https" in the subdomain text to look trustworthy
    f = features_dict("http://https-secure-paypal.evil.com/login")
    assert f["https_in_domain_text"] == 1.0


def test_clean_domain_no_https_text():
    f = features_dict("https://github.com/user/repo")
    assert f["https_in_domain_text"] == 0.0


# ---------------------------------------------------------------------------
# Regression: dead features must no longer exist in FEATURE_NAMES
# ---------------------------------------------------------------------------


def test_no_dead_hex_in_path_feature():
    """hex_in_path was always 0 and was removed."""
    assert "hex_in_path" not in FEATURE_NAMES


def test_no_dead_uuid_feature():
    """path_contains_uuid was always 0 and was removed."""
    assert "path_contains_uuid" not in FEATURE_NAMES


def test_no_duplicate_at_symbol_feature():
    """The old f30 was a duplicate of f4 — must appear exactly once."""
    assert FEATURE_NAMES.count("has_at_symbol") == 1
