"""
phishguard.models.trainer
==========================
Trains a Random Forest classifier on the URL feature dataset and
serialises the model with joblib (safer and faster than pickle).

Replaces ``src/RandomForestTraining.py``, which had:
- A hardcoded absolute path to a developer's local machine.
- ``pickle.dump()`` into the current working directory instead of models/.
- No stratified split.
- No precision/recall/F1 report.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


def train(
    dataset_csv: Path,
    output_model: Path,
    *,
    n_estimators: int = 300,
    max_depth: int = 20,
    min_samples_leaf: int = 2,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict:
    """
    Train a RandomForestClassifier and save it to *output_model*.

    Parameters
    ----------
    dataset_csv:
        Path to the feature CSV produced by ``builder.build_dataset()``.
    output_model:
        Destination path for the serialised model (.joblib).
    n_estimators, max_depth, min_samples_leaf:
        RandomForest hyperparameters.
    test_size:
        Fraction of data held out for evaluation.
    random_state:
        Seed for reproducibility.

    Returns
    -------
    dict
        ``{"accuracy": float, "roc_auc": float, "report": str}``
    """
    logger.info("Loading dataset from %s", dataset_csv)
    df = pd.read_csv(dataset_csv)

    X = df.drop("label", axis=1)
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,          # preserve class balance in both splits
    )
    logger.info("Train: %d rows  |  Test: %d rows", len(X_train), len(X_test))

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,           # use all CPU cores
    )

    logger.info("Training Random Forest (%d trees, max_depth=%d)…", n_estimators, max_depth)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_proba)
    report = classification_report(
        y_test, y_pred, target_names=["Legitimate", "Phishing"]
    )

    logger.info("Accuracy : %.4f", accuracy)
    logger.info("ROC-AUC  : %.4f", roc_auc)
    logger.info("\n%s", report)

    output_model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_model)
    logger.info("Model saved → %s", output_model)

    return {"accuracy": accuracy, "roc_auc": roc_auc, "report": report}
