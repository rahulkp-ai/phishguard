"""
phishguard.features.extractor
==============================
Extracts 28 hand-crafted URL features used by the phishing classifier.

Changes from the original feature_extractor.py
-----------------------------------------------
- Removed ``hex_in_path()``  — always returned 0, contributed nothing.
- Removed ``path_contains_uuid()`` — always returned 0, contributed nothing.
- Removed duplicate ``has_at_symbol()`` at position 30 (identical to f4).
- Result: 28 distinct, non-degenerate features.
- ``FEATURE_NAMES`` now uses human-readable names instead of f1..f30,
  making model introspection, logging, and the API response readable.
- Module is pure-function: no side effects on import.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Known-legitimate domain allowlist
# Used to suppress false positives on popular sites whose deep URLs
# (long paths, query strings, UUIDs) would otherwise trigger multiple
# features.
# ---------------------------------------------------------------------------
KNOWN_LEGITIMATE: frozenset[str] = frozenset(
    {
        "google.com",
        "youtube.com",
        "facebook.com",
        "twitter.com",
        "instagram.com",
        "linkedin.com",
        "microsoft.com",
        "apple.com",
        "amazon.com",
        "netflix.com",
        "github.com",
        "stackoverflow.com",
        "reddit.com",
        "wikipedia.org",
        "chatgpt.com",
        "openai.com",
        "coursera.org",
        "udemy.com",
        "gemini.google.com",
        "gmail.com",
        "outlook.com",
        "yahoo.com",
        "bing.com",
        "dropbox.com",
        "notion.so",
        "slack.com",
        "zoom.us",
        "twitch.tv",
        "spotify.com",
        "pinterest.com",
        "tiktok.com",
        "whatsapp.com",
        "telegram.org",
        "discord.com",
        "shopify.com",
        "ebay.com",
        "paypal.com",
        "stripe.com",
        "cloudflare.com",
        "wordpress.com",
        "medium.com",
        "substack.com",
        "canva.com",
        "figma.com",
        "adobe.com",
        "indiabix.com",
        "w3schools.com",
        "geeksforgeeks.org",
        "leetcode.com",
    }
)

# Human-readable names — one per extracted feature, in order.
FEATURE_NAMES: list[str] = [
    "has_ip",  # 0
    "url_length",  # 1
    "has_shortener",  # 2
    "has_at_symbol",  # 3
    "double_slash_redirect",  # 4
    "hyphen_in_domain",  # 5
    "subdomain_depth",  # 6
    "https_in_domain_text",  # 7
    "digit_ratio",  # 8
    "special_char_count",  # 9
    "slash_count",  # 10
    "dot_count",  # 11
    "suspicious_keywords",  # 12
    "domain_length",  # 13
    "has_exe_extension",  # 14
    "hyphen_count",  # 15
    "encoded_chars",  # 16
    "path_depth",  # 17
    "query_length",  # 18
    "domain_entropy",  # 19
    "suspicious_tld",  # 20
    "brand_in_subdomain",  # 21
    "non_standard_port",  # 22
    "digit_in_domain",  # 23
    "url_entropy",  # 24
    "repeated_chars",  # 25
    "dangerous_extension",  # 26
    "subdomain_count",  # 27
]

NUM_FEATURES: int = len(FEATURE_NAMES)  # 28


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entropy(s: str) -> float:
    """Shannon entropy of a string."""
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _get_root_domain(domain: str) -> str:
    """'sub.google.com' → 'google.com'"""
    domain = domain.lower().lstrip("www.")
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def _is_known_legit(domain: str) -> bool:
    return _get_root_domain(domain) in KNOWN_LEGITIMATE


# ---------------------------------------------------------------------------
# Individual feature functions
# Each returns a float in [0, 1].  Binary signals return exactly 0 or 1;
# graded signals return intermediate values to avoid hard thresholding.
# ---------------------------------------------------------------------------


def _has_ip(url: str) -> float:
    pattern = r"(([01]?\d\d?|2[0-4]\d|25[0-5])\.){3}([01]?\d\d?|2[0-4]\d|25[0-5])"
    return 1.0 if re.search(pattern, url) else 0.0


def _url_length(url: str) -> float:
    length = len(url)
    if length < 100:
        return 0.0
    if length < 190:
        return 0.3  # long but plausible (e.g. deep GitHub path)
    return 1.0  # very long → suspicious


def _has_shortener(url: str) -> float:
    pattern = r"bit\.ly|goo\.gl|tinyurl|t\.co|is\.gd|buff\.ly|ow\.ly|short\.to|adf\.ly|tiny\.cc"
    return 1.0 if re.search(pattern, url, re.I) else 0.0


def _has_at_symbol(url: str) -> float:
    # The @ character forces the browser to treat everything before it as
    # credentials, redirecting to whatever comes after — classic phishing trick.
    return 1.0 if "@" in url else 0.0


def _double_slash_redirect(url: str) -> float:
    return 1.0 if url.rfind("//") > 7 else 0.0


def _hyphen_in_domain(domain: str) -> float:
    return 1.0 if "-" in domain else 0.0


def _subdomain_depth(domain: str) -> float:
    domain = re.sub(r"^www\.", "", domain)
    dots = domain.count(".")
    if dots <= 1:
        return 0.0
    if dots == 2:
        return 0.3
    return 1.0


def _https_in_domain_text(domain: str) -> float:
    # Phishers sometimes embed "https" in the subdomain text itself to look
    # trustworthy: "https-paypal-secure.evil.com"
    return 1.0 if "https" in domain.lower() else 0.0


def _digit_ratio(url: str) -> float:
    if not url:
        return 0.0
    ratio = sum(c.isdigit() for c in url) / len(url)
    # Dampen: UUIDs in legitimate URLs (ChatGPT, Gemini) legitimately push
    # ratio high, so we halve the signal to reduce false positives.
    return round(min(ratio * 0.5, 1.0), 4)


def _special_char_count(url: str) -> float:
    # Query parameters are normal in legitimate apps; only flag excess.
    count = url.count("?") + url.count("=") + url.count("&")
    if count <= 5:
        return 0.0
    if count <= 10:
        return 0.5
    return 1.0


def _slash_count(url: str) -> float:
    # Coursera/YouTube have deep paths — raise threshold above 9.
    return 1.0 if url.count("/") > 9 else 0.0


def _dot_count(url: str) -> float:
    return 1.0 if url.count(".") > 6 else 0.0


def _suspicious_keywords(url: str) -> float:
    words = [
        "login",
        "secure",
        "account",
        "verify",
        "update",
        "password",
        "confirm",
        "support",
        "billing",
        "suspend",
        "unusual",
        "alert",
        "validation",
        "signin",
        "recover",
    ]
    url_lower = url.lower()
    hits = sum(1 for w in words if w in url_lower)
    if hits == 0:
        return 0.0
    if hits == 1:
        return 0.4
    return 1.0


def _domain_length(domain: str) -> float:
    core = re.sub(r"^www\.", "", domain).split(".")[0]
    return 1.0 if len(core) > 25 else 0.0


def _has_exe(url: str) -> float:
    return 1.0 if url.lower().endswith(".exe") else 0.0


def _hyphen_count(url: str) -> float:
    parsed = urlparse(url)
    # Only count hyphens in the netloc (domain), not the path.
    return 1.0 if parsed.netloc.count("-") > 3 else 0.0


def _encoded_chars(url: str) -> float:
    parsed = urlparse(url)
    # Percent-encoding in the path/query is normal; in the domain is suspicious.
    return 1.0 if "%" in parsed.netloc else 0.0


def _path_depth(url: str) -> float:
    parsed = urlparse(url)
    depth = len([p for p in parsed.path.split("/") if p])
    if depth <= 4:
        return 0.0
    if depth <= 7:
        return 0.3
    return 1.0


def _query_length(url: str) -> float:
    query = urlparse(url).query
    if len(query) < 50:
        return 0.0
    if len(query) < 150:
        return 0.3
    return 1.0


def _domain_entropy(domain: str) -> float:
    core = re.sub(r"^www\.", "", domain).split(".")[0]
    e = _entropy(core)
    if e < 3.2:
        return 0.0
    if e < 3.9:
        return 0.3
    return 1.0


def _suspicious_tld(domain: str) -> float:
    suspicious_tlds = {
        ".tk",
        ".ml",
        ".ga",
        ".cf",
        ".gq",
        ".xyz",
        ".top",
        ".click",
        ".link",
        ".online",
        ".site",
        ".biz",
    }
    domain_lower = domain.lower()
    return 1.0 if any(domain_lower.endswith(t) for t in suspicious_tlds) else 0.0


def _brand_in_subdomain(url: str) -> float:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    brands = [
        "paypal",
        "google",
        "amazon",
        "apple",
        "microsoft",
        "facebook",
        "netflix",
        "instagram",
        "twitter",
        "ebay",
    ]
    parts = domain.split(".")
    if len(parts) > 2:
        subdomain_part = ".".join(parts[:-2])
        return 1.0 if any(b in subdomain_part for b in brands) else 0.0
    return 0.0


def _non_standard_port(url: str) -> float:
    netloc = urlparse(url).netloc
    if ":" in netloc:
        try:
            port = int(netloc.split(":")[-1])
            if port not in {80, 443, 8080, 8443}:
                return 1.0
        except ValueError:
            pass
    return 0.0


def _digit_in_domain(domain: str) -> float:
    core = re.sub(r"^www\.", "", domain).split(".")[0]
    return 1.0 if any(c.isdigit() for c in core) else 0.0


def _url_entropy(url: str) -> float:
    # UUIDs in modern web apps push entropy up legitimately — only flag very high.
    e = _entropy(url)
    if e < 4.0:
        return 0.0
    if e < 4.6:
        return 0.3
    return 1.0


def _repeated_chars(url: str) -> float:
    # Four or more consecutive identical characters (raised from 3 to reduce FP).
    return 1.0 if re.search(r"(.)\1{4,}", url) else 0.0


def _dangerous_extension(url: str) -> float:
    path = urlparse(url).path.lower()
    dangerous = {".exe", ".bat", ".sh", ".cmd", ".vbs", ".ps1"}
    # .php/.asp intentionally excluded — too many legitimate sites use them.
    return 1.0 if any(path.endswith(ext) for ext in dangerous) else 0.0


def _subdomain_count(url: str) -> float:
    parsed = urlparse(url)
    domain = re.sub(r"^www\.", "", parsed.netloc)
    parts = domain.split(".")
    n = len(parts) - 2
    if n <= 0:
        return 0.0
    if n == 1:
        return 0.3
    return 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_features(url: str) -> list[float]:
    """
    Extract 28 URL features and return them as a list of floats.

    Parameters
    ----------
    url:
        A fully-qualified URL string (scheme required).

    Returns
    -------
    list[float]
        Exactly ``NUM_FEATURES`` (28) values, each in [0, 1].
        The order matches ``FEATURE_NAMES``.
    """
    parsed = urlparse(url)
    domain = parsed.netloc

    # Known-legit override: suppress path/length/query features that cause
    # false positives on deep URLs from popular sites.
    known = _is_known_legit(domain)

    features = [
        _has_ip(url),  # 0  has_ip
        0.0 if known else _url_length(url),  # 1  url_length
        _has_shortener(url),  # 2  has_shortener
        _has_at_symbol(url),  # 3  has_at_symbol
        _double_slash_redirect(url),  # 4  double_slash_redirect
        _hyphen_in_domain(domain),  # 5  hyphen_in_domain
        _subdomain_depth(domain),  # 6  subdomain_depth
        _https_in_domain_text(domain),  # 7  https_in_domain_text
        0.0 if known else _digit_ratio(url),  # 8  digit_ratio
        0.0 if known else _special_char_count(url),  # 9  special_char_count
        0.0 if known else _slash_count(url),  # 10 slash_count
        _dot_count(url),  # 11 dot_count
        0.0 if known else _suspicious_keywords(url),  # 12 suspicious_keywords
        _domain_length(domain),  # 13 domain_length
        _has_exe(url),  # 14 has_exe_extension
        _hyphen_count(url),  # 15 hyphen_count
        _encoded_chars(url),  # 16 encoded_chars
        0.0 if known else _path_depth(url),  # 17 path_depth
        0.0 if known else _query_length(url),  # 18 query_length
        _domain_entropy(domain),  # 19 domain_entropy
        _suspicious_tld(domain),  # 20 suspicious_tld
        _brand_in_subdomain(url),  # 21 brand_in_subdomain
        _non_standard_port(url),  # 22 non_standard_port
        _digit_in_domain(domain),  # 23 digit_in_domain
        0.0 if known else _url_entropy(url),  # 24 url_entropy
        _repeated_chars(url),  # 25 repeated_chars
        _dangerous_extension(url),  # 26 dangerous_extension
        _subdomain_count(url),  # 27 subdomain_count
    ]

    assert (
        len(features) == NUM_FEATURES
    ), f"Feature count mismatch: expected {NUM_FEATURES}, got {len(features)}"
    return features
