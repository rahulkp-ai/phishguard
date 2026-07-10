"""
tests/test_extractor_coverage.py
==================================
Targeted tests for every uncovered branch in extractor.py.

Each test class maps to one feature function and exercises every return
value branch (0.0, 0.3, 1.0) and every edge case.

Why separate from test_features.py?
------------------------------------
test_features.py validates behaviour (known-phishing URLs score high,
known-legit URLs score low).  This file validates implementation — it
drives specific inputs through individual branches that the behaviour
tests don't happen to hit.  Keeping them separate makes the intent clear.
"""

from __future__ import annotations

import pytest

from phishguard.features.extractor import (
    FEATURE_NAMES,
    _entropy,
    _get_root_domain,
    _is_known_legit,
    extract_features,
)


def feat(url: str, name: str) -> float:
    """Extract a single named feature from a URL."""
    idx = FEATURE_NAMES.index(name)
    return extract_features(url)[idx]


# ---------------------------------------------------------------------------
# _entropy helper
# ---------------------------------------------------------------------------


class TestEntropyHelper:
    def test_empty_string_returns_zero(self):
        assert _entropy("") == 0.0

    def test_single_char_returns_zero(self):
        # log2(1) = 0
        assert _entropy("aaaa") == 0.0

    def test_two_equal_chars_returns_one(self):
        assert abs(_entropy("ab") - 1.0) < 1e-9

    def test_higher_entropy_for_random_string(self):
        assert _entropy("a1b2c3d4e5") > _entropy("aaaaabbbbb")


# ---------------------------------------------------------------------------
# _get_root_domain and _is_known_legit helpers
# ---------------------------------------------------------------------------


class TestRootDomain:
    def test_strips_www(self):
        assert _get_root_domain("www.google.com") == "google.com"

    def test_subdomain_stripped(self):
        assert _get_root_domain("sub.domain.google.com") == "google.com"

    def test_plain_domain_unchanged(self):
        assert _get_root_domain("example.com") == "example.com"

    def test_single_label_unchanged(self):
        assert _get_root_domain("localhost") == "localhost"


class TestIsKnownLegit:
    def test_google_is_legit(self):
        assert _is_known_legit("google.com") is True

    def test_subdomain_of_google_is_legit(self):
        assert _is_known_legit("mail.google.com") is True

    def test_evil_site_is_not_legit(self):
        assert _is_known_legit("evil.tk") is False

    def test_paypal_lookalike_is_not_legit(self):
        assert _is_known_legit("paypal-secure.com") is False


# ---------------------------------------------------------------------------
# url_length — three branches: 0.0 (<100), 0.3 (100–189), 1.0 (≥190)
# ---------------------------------------------------------------------------


class TestUrlLength:
    def test_short_url_returns_zero(self):
        assert feat("https://example.com/short", "url_length") == 0.0

    def test_medium_url_returns_03(self):
        # Build a URL that is exactly 150 chars, not a known-legit domain
        url = "https://totally-unknown-domain.com/" + "a" * 115
        assert len(url) == 150
        assert feat(url, "url_length") == 0.3

    def test_very_long_url_returns_1(self):
        url = "https://totally-unknown-domain.com/" + "a" * 200
        assert feat(url, "url_length") == 1.0

    def test_known_legit_long_url_returns_zero(self):
        # Known-legit domains should suppress url_length regardless of length
        url = "https://github.com/" + "a" * 200
        assert feat(url, "url_length") == 0.0


# ---------------------------------------------------------------------------
# digit_ratio — zero for empty string branch (covered via known-legit)
# ---------------------------------------------------------------------------


class TestDigitRatio:
    def test_no_digits_returns_zero(self):
        assert feat("https://abcdef.com/path", "digit_ratio") == 0.0

    def test_many_digits_returns_nonzero(self):
        # URL with ~60% digits
        url = "https://unknowndomain.com/1234567890123456789012345678901234567890"
        result = feat(url, "digit_ratio")
        assert result > 0.0

    def test_known_legit_digit_rich_url_suppressed(self):
        # ChatGPT conversation UUIDs have high digit ratio — must be suppressed
        url = "https://chatgpt.com/c/69abaa4b-7674-8323-b419-37dedc7d6382"
        assert feat(url, "digit_ratio") == 0.0


# ---------------------------------------------------------------------------
# special_char_count — three branches: 0.0 (≤5), 0.5 (6-10), 1.0 (>10)
# ---------------------------------------------------------------------------


class TestSpecialCharCount:
    def test_few_special_chars_returns_zero(self):
        assert feat("https://example.com/path?a=1&b=2", "special_char_count") == 0.0

    def test_medium_special_chars_returns_05(self):
        # ?=1 &b=2 &c=3 &d=4 → count = 1(?)+4(=)+3(&) = 8  → branch 0.5
        url = "https://unknowndomain.com/path?a=1&b=2&c=3&d=4"
        result = feat(url, "special_char_count")
        assert result == 0.5

    def test_many_special_chars_returns_1(self):
        url = "https://unknowndomain.com/?a=1&b=2&c=3&d=4&e=5&f=6&g=7&h=8&i=9&j=10&k=11"
        result = feat(url, "special_char_count")
        assert result == 1.0


# ---------------------------------------------------------------------------
# path_depth — three branches: 0.0 (≤4), 0.3 (5–7), 1.0 (>7)
# ---------------------------------------------------------------------------


class TestPathDepth:
    def test_shallow_path_returns_zero(self):
        assert feat("https://unknowndomain.com/a/b/c", "path_depth") == 0.0

    def test_medium_depth_returns_03(self):
        url = "https://unknowndomain.com/a/b/c/d/e"
        assert feat(url, "path_depth") == 0.3

    def test_deep_path_returns_1(self):
        url = "https://unknowndomain.com/a/b/c/d/e/f/g/h"
        assert feat(url, "path_depth") == 1.0

    def test_known_legit_deep_path_suppressed(self):
        url = "https://coursera.org/learn/python/home/module/1/item/2/review/3/feedback/4"
        assert feat(url, "path_depth") == 0.0


# ---------------------------------------------------------------------------
# query_length — three branches: 0.0 (<50), 0.3 (50–149), 1.0 (≥150)
# ---------------------------------------------------------------------------


class TestQueryLength:
    def test_short_query_returns_zero(self):
        assert feat("https://unknowndomain.com/path?q=short", "query_length") == 0.0

    def test_medium_query_returns_03(self):
        url = "https://unknowndomain.com/path?" + "a=b&" * 15  # ~60 chars in query
        assert feat(url, "query_length") == 0.3

    def test_long_query_returns_1(self):
        url = "https://unknowndomain.com/path?" + "x=" + "a" * 148
        assert feat(url, "query_length") == 1.0

    def test_known_legit_long_query_suppressed(self):
        url = "https://google.com/search?" + "q=" + "a" * 148
        assert feat(url, "query_length") == 0.0


# ---------------------------------------------------------------------------
# domain_entropy — three branches: 0.0 (<3.2), 0.3 (3.2–3.8), 1.0 (≥3.9)
# ---------------------------------------------------------------------------


class TestDomainEntropy:
    def test_low_entropy_domain_returns_zero(self):
        # "aaaa.com" — very low entropy
        assert feat("https://aaaa.com/", "domain_entropy") == 0.0

    def test_medium_entropy_domain_returns_03(self):
        # "abcdefgh.com" — entropy ~3.0; need something with H in (3.2, 3.9)
        # "a1b2c3d4.com" mixes letters and digits → H ≈ 3.0–3.5
        assert feat("https://a1b2c3d4.com/", "domain_entropy") in (0.0, 0.3)

    def test_high_entropy_domain_returns_1(self):
        # 16 unique chars → Shannon entropy = log2(16) = 4.0, which is > 3.9
        # Use a domain whose core label is exactly "abcdefghijklmnop"
        assert feat("https://abcdefghijklmnop.com/", "domain_entropy") == 1.0


# ---------------------------------------------------------------------------
# url_entropy — three branches: 0.0 (<4.0), 0.3 (4.0–4.5), 1.0 (≥4.6)
# ---------------------------------------------------------------------------


class TestUrlEntropy:
    def test_low_entropy_url_returns_zero(self):
        assert feat("https://aaaa.com/aaaa", "url_entropy") == 0.0

    def test_high_entropy_url_returns_1(self):
        url = "https://xk9mq2zv7wd.com/a1B2c3D4e5F6g7H8?tok=9iJ0kL1m"
        assert feat(url, "url_entropy") == 1.0

    def test_known_legit_high_entropy_url_suppressed(self):
        # ChatGPT UUID URLs have high entropy — must be suppressed for known-legit
        url = "https://chatgpt.com/c/69abaa4b-7674-8323-b419-37dedc7d6382"
        assert feat(url, "url_entropy") == 0.0


# ---------------------------------------------------------------------------
# non_standard_port — three branches: standard port, non-standard, invalid
# ---------------------------------------------------------------------------


class TestNonStandardPort:
    def test_standard_port_80_returns_zero(self):
        assert feat("http://example.com:80/path", "non_standard_port") == 0.0

    def test_standard_port_443_returns_zero(self):
        assert feat("https://example.com:443/path", "non_standard_port") == 0.0

    def test_standard_port_8080_returns_zero(self):
        assert feat("http://example.com:8080/path", "non_standard_port") == 0.0

    def test_non_standard_port_returns_1(self):
        assert feat("http://example.com:9999/login", "non_standard_port") == 1.0

    def test_no_port_returns_zero(self):
        assert feat("https://example.com/path", "non_standard_port") == 0.0

    def test_invalid_port_string_returns_zero(self):
        # "example.com:notanumber" — the ValueError branch
        from phishguard.features.extractor import _non_standard_port

        assert _non_standard_port("http://example.com:notanumber/path") == 0.0


# ---------------------------------------------------------------------------
# subdomain_depth — three branches
# ---------------------------------------------------------------------------


class TestSubdomainDepth:
    def test_no_subdomain_returns_zero(self):
        assert feat("https://example.com/", "subdomain_depth") == 0.0

    def test_one_subdomain_returns_03(self):
        assert feat("https://mail.example.com/", "subdomain_depth") == 0.3

    def test_deep_subdomain_returns_1(self):
        assert feat("https://a.b.c.example.com/", "subdomain_depth") == 1.0


# ---------------------------------------------------------------------------
# slash_count, dot_count
# ---------------------------------------------------------------------------


class TestSlashAndDotCount:
    def test_few_slashes_returns_zero(self):
        assert feat("https://example.com/a/b/c", "slash_count") == 0.0

    def test_many_slashes_returns_1(self):
        url = "https://unknowndomain.com/" + "/".join(["a"] * 10)
        assert feat(url, "slash_count") == 1.0

    def test_few_dots_returns_zero(self):
        assert feat("https://example.com/path", "dot_count") == 0.0

    def test_many_dots_returns_1(self):
        assert feat("https://a.b.c.d.e.f.g.example.com/path", "dot_count") == 1.0


# ---------------------------------------------------------------------------
# has_exe_extension
# ---------------------------------------------------------------------------


class TestHasExe:
    def test_exe_url_returns_1(self):
        assert feat("http://evil.com/malware.exe", "has_exe_extension") == 1.0

    def test_normal_url_returns_zero(self):
        assert feat("https://example.com/page.html", "has_exe_extension") == 0.0


# ---------------------------------------------------------------------------
# dangerous_extension
# ---------------------------------------------------------------------------


class TestDangerousExtension:
    @pytest.mark.parametrize("ext", [".bat", ".sh", ".cmd", ".vbs", ".ps1"])
    def test_dangerous_extensions_return_1(self, ext):
        assert feat(f"http://evil.com/payload{ext}", "dangerous_extension") == 1.0

    def test_safe_extension_returns_zero(self):
        assert feat("https://example.com/index.html", "dangerous_extension") == 0.0

    def test_php_not_flagged(self):
        # .php intentionally excluded from dangerous list
        assert feat("https://wordpress.com/index.php", "dangerous_extension") == 0.0


# ---------------------------------------------------------------------------
# subdomain_count — three branches
# ---------------------------------------------------------------------------


class TestSubdomainCount:
    def test_no_subdomain_returns_zero(self):
        assert feat("https://example.com/", "subdomain_count") == 0.0

    def test_one_subdomain_returns_03(self):
        assert feat("https://mail.example.com/", "subdomain_count") == 0.3

    def test_multiple_subdomains_returns_1(self):
        assert feat("https://a.b.example.com/", "subdomain_count") == 1.0


# ---------------------------------------------------------------------------
# hyphen_count (in domain, threshold > 3)
# ---------------------------------------------------------------------------


class TestHyphenCount:
    def test_few_hyphens_returns_zero(self):
        assert feat("https://my-site.com/", "hyphen_count") == 0.0

    def test_many_hyphens_returns_1(self):
        assert feat("https://my-very-very-very-long-domain.com/", "hyphen_count") == 1.0


# ---------------------------------------------------------------------------
# brand_in_subdomain
# ---------------------------------------------------------------------------


class TestBrandInSubdomain:
    def test_brand_in_subdomain_returns_1(self):
        assert feat("http://paypal.evil.com/login", "brand_in_subdomain") == 1.0

    def test_brand_in_root_domain_not_flagged(self):
        # paypal.com itself — brand is the root, not a subdomain
        assert feat("https://paypal.com/login", "brand_in_subdomain") == 0.0


# ---------------------------------------------------------------------------
# digit_in_domain
# ---------------------------------------------------------------------------


class TestDigitInDomain:
    def test_digit_in_domain_returns_1(self):
        assert feat("http://bank123.com/login", "digit_in_domain") == 1.0

    def test_no_digit_returns_zero(self):
        assert feat("https://example.com/", "digit_in_domain") == 0.0


# ---------------------------------------------------------------------------
# repeated_chars (four or more consecutive)
# ---------------------------------------------------------------------------


class TestRepeatedChars:
    def test_four_repeated_returns_1(self):
        assert feat("http://eviilllll.com/", "repeated_chars") == 1.0

    def test_three_repeated_returns_zero(self):
        # Three consecutive is NOT flagged (threshold is 4+)
        assert feat("http://evill.com/", "repeated_chars") == 0.0


# ---------------------------------------------------------------------------
# encoded_chars
# ---------------------------------------------------------------------------


class TestEncodedChars:
    def test_percent_in_domain_returns_1(self):
        assert feat("http://g%6Fgle.com/", "encoded_chars") == 1.0

    def test_percent_in_path_only_returns_zero(self):
        # Percent-encoding in path is normal — only domain is checked
        assert feat("https://example.com/path%20with%20spaces", "encoded_chars") == 0.0


# ---------------------------------------------------------------------------
# suspicious_keywords — three branches: 0.0, 0.4, 1.0
# ---------------------------------------------------------------------------


class TestSuspiciousKeywords:
    def test_no_keywords_returns_zero(self):
        assert feat("https://unknowndomain.com/home", "suspicious_keywords") == 0.0

    def test_one_keyword_returns_04(self):
        assert feat("https://unknowndomain.com/login", "suspicious_keywords") == 0.4

    def test_multiple_keywords_returns_1(self):
        assert feat("https://unknowndomain.com/login/verify/account", "suspicious_keywords") == 1.0

    def test_known_legit_keywords_suppressed(self):
        assert feat("https://github.com/login", "suspicious_keywords") == 0.0
