"""Entraînement du modèle de détection de fraude (apprentissage SUPERVISÉ, classes déséquilibrées).

Pourquoi supervisé : on dispose d'étiquettes (Class = 1 si fraude) -> classification binaire.
Pourquoi pas l'accuracy : 99,8 % des transactions sont légitimes ; un modèle qui dit toujours
« pas de fraude » aurait 99,8 % d'accuracy et ne servirait à rien. On utilise donc :
  - l'AUC-PR (average precision) pour comparer les modèles ;
  - précision / rappel au seuil choisi pour l'usage métier.
Démarche :
  1. découpage stratifié train 60 % / validation 20 % / test 20 % ;
  2. comparaison d'une baseline (régression logistique) et d'un modèle plus puissant (HistGradientBoosting) ;
  3. choix du seuil sur la validation (F1 max) — jamais sur le test ;
  4. évaluation finale unique sur le test ;
  5. sauvegarde du modèle + carte d'identité (métriques, temps, taille) pour la traçabilité.

Lancement : python -m src.ml.fraud_train [--source csv|db]
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src import config
from src.logging_conf import get_logger
from src.ml.features import FEATURES, build_features

log = get_logger(__name__)
MODEL_PATH = config.MODELS_DIR / "fraud_model.joblib"
METRICS_PATH = config.MODELS_DIR / "fraud_metrics.json"


def load_data(source: str) -> pd.DataFrame:
    if source == "db":
        from src.db.postgres import fetch_df

        return fetch_df("SELECT * FROM fact_transaction ORDER BY transaction_id")
    from src.collect.kaggle_fraud import read_creditcard
    from src.transform.transactions import clean_transactions

    df, _ = clean_transactions(read_creditcard())
    return df


def candidate_models() -> dict:
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000)
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, class_weight="balanced",
            early_stopping=True, random_state=42,
        ),
    }


def best_threshold(y_true, proba) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    return float(thresholds[int(np.argmax(f1[:-1]))])


def train(df: pd.DataFrame) -> dict:
    X = build_features(df)
    y = df["is_fraud"].astype(int).to_numpy()
    X_train, X_tmp, y_train, y_tmp = train_test_split(X, y, test_size=0.4, stratify=y, random_state=42)
    X_val, X_test, y_val, y_test = train_test_split(X_tmp, y_tmp, test_size=0.5, stratify=y_tmp, random_state=42)

    comparison = {}
    fitted = {}
    for name, model in candidate_models().items():
        t0 = time.perf_counter()
        model.fit(X_train, y_train)
        fit_s = time.perf_counter() - t0
        ap = average_precision_score(y_val, model.predict_proba(X_val)[:, 1])
        comparison[name] = {"val_average_precision": round(ap, 4), "fit_seconds": round(fit_s, 2)}
        fitted[name] = model
        log.info("%s : AUC-PR validation = %.4f (%.1f s)", name, ap, fit_s)

    best_name = max(comparison, key=lambda n: comparison[n]["val_average_precision"])
    model = fitted[best_name]
    threshold = best_threshold(y_val, model.predict_proba(X_val)[:, 1])

    proba_test = model.predict_proba(X_test)[:, 1]
    pred_test = (proba_test >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, pred_test, labels=[0, 1]).ravel()
    t0 = time.perf_counter()
    model.predict_proba(X_test)
    latency_ms = (time.perf_counter() - t0) / len(X_test) * 1000

    version = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    metrics = {
        "model_version": version,
        "selected_model": best_name,
        "comparison": comparison,
        "threshold": round(threshold, 6),
        "test": {
            "average_precision": round(average_precision_score(y_test, proba_test), 4),
            "roc_auc": round(roc_auc_score(y_test, proba_test), 4),
            "precision": round(precision_score(y_test, pred_test, zero_division=0), 4),
            "recall": round(recall_score(y_test, pred_test, zero_division=0), 4),
            "f1": round(f1_score(y_test, pred_test, zero_division=0), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
        "n_train": int(len(y_train)),
        "n_val": int(len(y_val)),
        "n_test": int(len(y_test)),
        "fraud_rate": round(float(y.mean()), 5),
        "latency_ms_per_tx": round(latency_ms, 5),
        "features": FEATURES,
    }

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "threshold": threshold, "features": FEATURES, "version": version},
        MODEL_PATH,
    )
    metrics["model_size_kb"] = round(MODEL_PATH.stat().st_size / 1024, 1)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    log.info("Modèle %s sauvegardé (%s) - test : %s", best_name, version, metrics["test"])
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Entraîne le modèle de détection de fraude")
    parser.add_argument("--source", choices=["csv", "db"], default="db")
    args = parser.parse_args()
    metrics = train(load_data(args.source))
    print(json.dumps(metrics["test"], indent=2))


if __name__ == "__main__":
    main()
