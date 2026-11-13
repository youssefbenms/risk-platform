"""API REST de la plateforme de gestion des risques (FastAPI).

Sécurité :
  - toutes les routes /v1 exigent l'en-tête X-API-Key (comparaison à temps constant) ;
  - validation stricte des entrées par Pydantic (types, bornes) -> erreur 422 sinon ;
  - requêtes SQL paramétrées uniquement ;
  - aucun détail interne renvoyé en cas d'erreur 500.
Observabilité : /metrics au format Prometheus (latence, nombre de requêtes, codes HTTP).
Documentation interactive : http://localhost:8000/docs
"""
from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from functools import lru_cache

import joblib
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from src import config
from src.db.mongo import get_db
from src.db.postgres import fetch_df
from src.logging_conf import get_logger
from src.ml.features import build_features

log = get_logger(__name__)
MODEL_PATH = config.MODELS_DIR / "fraud_model.joblib"

app = FastAPI(
    title="Risk Platform API",
    version="1.0.0",
    description="Détection de fraude, indicateurs de risque de marché et veille BCE.",
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    import os

    expected = os.getenv("API_KEY", config.API_KEY)
    if not key or not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=401, detail="Clé API invalide ou absente")


@lru_cache(maxsize=1)
def load_model() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(MODEL_PATH)
    return joblib.load(MODEL_PATH)


# ------------------------------------------------------------------ schémas
class Transaction(BaseModel):
    time_offset_s: float = Field(ge=0, description="Secondes depuis le début de la période")
    amount: float = Field(ge=0, le=1_000_000, description="Montant en euros")
    v: list[float] = Field(min_length=28, max_length=28, description="Composantes ACP V1..V28")


class FraudScore(BaseModel):
    fraud_probability: float
    is_fraud: bool
    threshold: float
    model_version: str


class RiskPoint(BaseModel):
    ticker: str
    metric_date: date
    log_return: float | None
    vol_20d_ann: float | None
    var_95_hist: float | None
    var_99_hist: float | None
    var_95_param: float | None
    is_anomaly: bool | None


# ------------------------------------------------------------------ routes
@app.get("/health", tags=["monitoring"])
def health() -> dict:
    """Sonde de vie (utilisée par Docker et Kubernetes) : ne dépend d'aucune base."""
    return {"status": "ok", "model_loaded": MODEL_PATH.exists()}


@app.post("/v1/fraud/score", response_model=FraudScore, tags=["fraude"],
          dependencies=[Depends(require_api_key)])
def score_transaction(tx: Transaction) -> FraudScore:
    try:
        bundle = load_model()
    except FileNotFoundError as err:
        raise HTTPException(status_code=503, detail="Modèle non disponible : lancer l'entraînement") from err
    row = {"time_offset_s": tx.time_offset_s, "amount": tx.amount}
    row.update({f"v{i + 1}": val for i, val in enumerate(tx.v)})
    proba = float(bundle["model"].predict_proba(build_features(pd.DataFrame([row])))[:, 1][0])
    result = FraudScore(
        fraud_probability=round(proba, 6),
        is_fraud=proba >= bundle["threshold"],
        threshold=round(float(bundle["threshold"]), 6),
        model_version=bundle["version"],
    )
    try:  # journal d'audit des décisions (sans les variables d'entrée détaillées)
        get_db().prediction_logs.insert_one(
            {"created_at": datetime.now(UTC), "amount": tx.amount, **result.model_dump()}
        )
    except Exception:
        log.warning("Journal de prédiction indisponible (MongoDB)")
    return result


@app.get("/v1/assets", tags=["risque"], dependencies=[Depends(require_api_key)])
def list_assets() -> list[dict]:
    df = fetch_df("SELECT ticker, asset_class, currency FROM dim_asset ORDER BY ticker")
    return df.to_dict(orient="records")


@app.get("/v1/risk/{ticker}", response_model=list[RiskPoint], tags=["risque"],
         dependencies=[Depends(require_api_key)])
def risk_history(ticker: str, days: int = Query(30, ge=1, le=2000)) -> list[RiskPoint]:
    df = fetch_df(
        """
        SELECT a.ticker, r.metric_date, r.log_return, r.vol_20d_ann, r.var_95_hist,
               r.var_99_hist, r.var_95_param, r.is_anomaly
        FROM risk_metrics r JOIN dim_asset a ON a.asset_id = r.asset_id
        WHERE a.ticker = :ticker
        ORDER BY r.metric_date DESC
        LIMIT :days
        """,
        {"ticker": ticker.lower(), "days": days},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Aucune métrique pour {ticker}")
    df = df.astype(object).where(df.notna(), None)
    return [RiskPoint(**rec) for rec in df.to_dict(orient="records")]


@app.get("/v1/risk/alerts/latest", tags=["risque"], dependencies=[Depends(require_api_key)])
def latest_alerts(limit: int = Query(20, ge=1, le=200)) -> list[dict]:
    """Journées de marché détectées comme anormales par l'Isolation Forest."""
    df = fetch_df(
        """
        SELECT a.ticker, r.metric_date, r.log_return, r.anomaly_score
        FROM risk_metrics r JOIN dim_asset a ON a.asset_id = r.asset_id
        WHERE r.is_anomaly = :flag
        ORDER BY r.metric_date DESC
        LIMIT :limit
        """,
        {"flag": True, "limit": limit},
    )
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


@app.get("/v1/news", tags=["veille"], dependencies=[Depends(require_api_key)])
def latest_news(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    cursor = get_db().news_articles.find({}, {"_id": 0, "body": 0}).sort("published_at", -1).limit(limit)
    return list(cursor)
