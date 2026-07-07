"""
tests/test_config.py
====================
Tests for application configuration classes.
"""

from __future__ import annotations

import pytest

from app.config import DevelopmentConfig, ProductionConfig, TestingConfig


class TestProductionConfig:
    def test_validate_raises_when_secret_key_empty(self):
        original = ProductionConfig.SECRET_KEY
        ProductionConfig.SECRET_KEY = ""
        try:
            with pytest.raises(RuntimeError, match="SECRET_KEY"):
                ProductionConfig.validate()
        finally:
            ProductionConfig.SECRET_KEY = original

    def test_validate_passes_when_secret_key_set(self):
        original = ProductionConfig.SECRET_KEY
        ProductionConfig.SECRET_KEY = "a-real-secret-key-32-chars-long!!"
        try:
            ProductionConfig.validate()  # must not raise
        finally:
            ProductionConfig.SECRET_KEY = original

    def test_production_debug_is_false(self):
        assert ProductionConfig.DEBUG is False


class TestDevelopmentConfig:
    def test_debug_is_true(self):
        assert DevelopmentConfig.DEBUG is True

    def test_has_fallback_secret_key(self):
        # Dev config must have a non-empty fallback so the server starts
        # without setting SECRET_KEY in the environment.
        assert len(DevelopmentConfig.SECRET_KEY) > 0


class TestTestingConfig:
    def test_testing_is_true(self):
        assert TestingConfig.TESTING is True

    def test_has_secret_key(self):
        assert TestingConfig.SECRET_KEY == "testing-secret"


class TestModelPath:
    def test_model_path_ends_with_joblib(self):
        assert str(DevelopmentConfig.MODEL_PATH).endswith(".joblib")

    def test_model_path_contains_models_dir(self):
        assert "models" in str(DevelopmentConfig.MODEL_PATH)
