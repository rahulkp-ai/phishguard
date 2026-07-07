"""
phishguard.data.builder
========================
Builds the URL feature dataset from phishing + legitimate URL lists.

The original dataset_builder.py executed all its logic at module level,
which meant any import of the file triggered full dataset processing and
crashed if the data files didn't exist.  This module wraps all logic in
``build_dataset()`` — nothing runs on import.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from phishguard.features.extractor import FEATURE_NAMES, extract_features

logger = logging.getLogger(__name__)


def _load_urls(filepath: Path, label: int) -> tuple[list[str], list[int]]:
    """Read one URL per line from *filepath*, return (urls, labels)."""
    urls: list[str] = []
    with filepath.open() as f:
        for line in f:
            u = line.strip()
            if u:
                urls.append(u)
    return urls, [label] * len(urls)


def build_dataset(
    phishing_file: Path,
    legit_file: Path,
    output_csv: Path,
    *,
    balance: bool = True,
) -> pd.DataFrame:
    """
    Extract features from URL files and write a balanced CSV dataset.

    Parameters
    ----------
    phishing_file:
        Path to a text file with one phishing URL per line.
    legit_file:
        Path to a text file with one legitimate URL per line.
    output_csv:
        Destination path for the resulting CSV.
    balance:
        If ``True``, truncate the larger class so both classes are equal size.

    Returns
    -------
    pd.DataFrame
        The completed dataset (also written to *output_csv*).
    """
    phish_urls, phish_labels = _load_urls(phishing_file, label=1)
    legit_urls, legit_labels = _load_urls(legit_file, label=0)

    if balance:
        n = min(len(phish_urls), len(legit_urls))
        phish_urls, phish_labels = phish_urls[:n], phish_labels[:n]
        legit_urls, legit_labels = legit_urls[:n], legit_labels[:n]
        logger.info("Balanced dataset: %d phishing + %d legitimate = %d total", n, n, n * 2)
    else:
        logger.info(
            "Unbalanced dataset: %d phishing + %d legitimate = %d total",
            len(phish_urls),
            len(legit_urls),
            len(phish_urls) + len(legit_urls),
        )

    all_urls = phish_urls + legit_urls
    all_labels = phish_labels + legit_labels

    rows: list[list] = []
    errors = 0
    total = len(all_urls)

    for i, (url, label) in enumerate(zip(all_urls, all_labels)):
        try:
            rows.append(extract_features(url) + [label])
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.debug("Skipping URL %s — %s", url, exc)
        if (i + 1) % 5000 == 0:
            logger.info("  %d / %d processed...", i + 1, total)

    if errors:
        logger.warning("%d URLs skipped due to errors", errors)

    df = pd.DataFrame(rows, columns=FEATURE_NAMES + ["label"])
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    logger.info("Dataset saved → %s  shape=%s", output_csv, df.shape)
    logger.info(
        "Class distribution:\n%s",
        df["label"].value_counts().to_string(),
    )
    return df
