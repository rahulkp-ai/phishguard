"""
tests/test_integration_trainer.py
===================================
Integration tests for ``phishguard.models.trainer.train()``.

These tests build a synthetic feature CSV (200 rows, 28 features),
call ``train()``, and assert on the returned metrics and the saved model.
No network access, no real URL data.

Marked ``integration`` — runs with ``pytest -m integration``.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from phishguard.features.extractor import FEATURE_NAMES, NUM_FEATURES
from phishguard.models.trainer import train

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_csv(tmp_path) -> Path:
    """
    Write a 200-row synthetic feature CSV to a temp file.

    Rows 0–99 are class 0 (legitimate): features biased toward 0.
    Rows 100–199 are class 1 (phishing):  features biased toward 1.
    This gives the Random Forest something genuinely separable to learn.
    """
    rng = np.random.default_rng(42)
    legit  = rng.uniform(0.0, 0.3, (100, NUM_FEATURES))
    phish  = rng.uniform(0.7, 1.0, (100, NUM_FEATURES))
    X = np.vstack([legit, phish])
    y = np.array([0] * 100 + [1] * 100)

    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df["label"] = y
    out = tmp_path / "dataset.csv"
    df.to_csv(out, index=False)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrainOutput:
    def test_model_file_is_created(self, synthetic_csv, tmp_path):
        model_path = tmp_path / "model.joblib"
        train(synthetic_csv, model_path)
        assert model_path.exists()

    def test_saved_model_is_random_forest(self, synthetic_csv, tmp_path):
        model_path = tmp_path / "model.joblib"
        train(synthetic_csv, model_path)
        model = joblib.load(model_path)
        assert isinstance(model, RandomForestClassifier)

    def test_models_dir_created_if_missing(self, synthetic_csv, tmp_path):
        model_path = tmp_path / "nested" / "models" / "model.joblib"
        train(synthetic_csv, model_path)
        assert model_path.exists()


class TestTrainMetrics:
    def test_returns_accuracy_key(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert "accuracy" in metrics

    def test_returns_roc_auc_key(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert "roc_auc" in metrics

    def test_returns_report_key(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert "report" in metrics

    def test_accuracy_is_float_in_unit_interval(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert isinstance(metrics["accuracy"], float)
        assert 0.0 <= metrics["accuracy"] <= 1.0

    def test_roc_auc_is_float_in_unit_interval(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert isinstance(metrics["roc_auc"], float)
        assert 0.0 <= metrics["roc_auc"] <= 1.0

    def test_report_contains_class_names(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert "Legitimate" in metrics["report"]
        assert "Phishing" in metrics["report"]

    def test_high_accuracy_on_separable_data(self, synthetic_csv, tmp_path):
        """
        The synthetic data is highly separable (legit ≈ 0.0–0.3,
        phishing ≈ 0.7–1.0), so accuracy should be well above chance.
        """
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert metrics["accuracy"] >= 0.85

    def test_high_roc_auc_on_separable_data(self, synthetic_csv, tmp_path):
        metrics = train(synthetic_csv, tmp_path / "model.joblib")
        assert metrics["roc_auc"] >= 0.90


class TestTrainPredictions:
    def test_saved_model_can_predict(self, synthetic_csv, tmp_path):
        model_path = tmp_path / "model.joblib"
        train(synthetic_csv, model_path)
        model = joblib.load(model_path)

        # Build a clearly-phishing row (all features = 1.0)
        X_phish = pd.DataFrame(
            [[1.0] * NUM_FEATURES], columns=FEATURE_NAMES
        )
        pred = model.predict(X_phish)[0]
        assert pred == 1

    def test_saved_model_returns_probabilities(self, synthetic_csv, tmp_path):
        model_path = tmp_path / "model.joblib"
        train(synthetic_csv, model_path)
        model = joblib.load(model_path)

        X = pd.DataFrame([[0.5] * NUM_FEATURES], columns=FEATURE_NAMES)
        proba = model.predict_proba(X)[0]
        assert len(proba) == 2
        assert abs(sum(proba) - 1.0) < 1e-6

    def test_model_has_feature_names(self, synthetic_csv, tmp_path):
        """Trainer must fit with named DataFrame so sklearn stores feature names."""
        model_path = tmp_path / "model.joblib"
        train(synthetic_csv, model_path)
        model = joblib.load(model_path)
        assert list(model.feature_names_in_) == FEATURE_NAMES


class TestTrainHyperparameters:
    def test_custom_n_estimators(self, synthetic_csv, tmp_path):
        train(synthetic_csv, tmp_path / "model.joblib", n_estimators=10)
        model = joblib.load(tmp_path / "model.joblib")
        assert model.n_estimators == 10

    def test_custom_test_size(self, synthetic_csv, tmp_path):
        """A smaller test split should still produce valid metrics."""
        metrics = train(synthetic_csv, tmp_path / "model.joblib", test_size=0.1)
        assert 0.0 <= metrics["accuracy"] <= 1.0
