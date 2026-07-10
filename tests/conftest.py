"""
Shared pytest fixtures and configuration.

Custom CLI options
------------------
--fast    Skip tests marked ``integration`` or ``slow``.
          Use this for the tight inner-loop feedback cycle.
          CI runs both passes: fast first, then full.

    pytest --fast          # unit tests only (~0.5s)
    pytest                 # full suite including integration tests
    pytest -m integration  # integration tests only
"""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from app import create_app
from app.config import TestingConfig
from phishguard.features.extractor import FEATURE_NAMES, NUM_FEATURES

# ---------------------------------------------------------------------------
# Custom CLI option
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--fast",
        action="store_true",
        default=False,
        help="Skip integration and slow tests for fast feedback.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--fast"):
        return
    skip_slow = pytest.mark.skip(reason="Skipped with --fast flag")
    for item in items:
        if "integration" in item.keywords or "slow" in item.keywords:
            item.add_marker(skip_slow)


# ---------------------------------------------------------------------------
# Minimal model fixture
# ---------------------------------------------------------------------------


def _make_tiny_model(model_path):
    """Train a 5-tree Random Forest on 20 synthetic rows and save it."""
    rng = np.random.default_rng(42)
    X = pd.DataFrame(rng.random((20, NUM_FEATURES)), columns=FEATURE_NAMES)
    y = np.array([0, 1] * 10)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)
    joblib.dump(clf, model_path)
    return clf


# ---------------------------------------------------------------------------
# App fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(tmp_path):
    """Flask app configured for testing, with a tiny model available."""
    model_path = tmp_path / "phishing_model.joblib"
    _make_tiny_model(model_path)

    class _TestConfig(TestingConfig):
        MODEL_PATH = model_path

    application = create_app(_TestConfig)
    yield application


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()
