"""Pipeline ETL complet : Extraction -> Transformation -> Contrôle qualité -> Chargement.

Chaque étape :
  - est idempotente (upsert : relancer = même résultat, pas de doublon) ;
  - est chronométrée et tracée dans etl_run_log (succès/échec, volumes, durée) ;
  - écrit ses contrôles qualité dans data_quality_check ;
  - s'arrête (exception) si un contrôle bloquant échoue.

Lancement manuel :      python -m src.etl.pipeline                 (toutes les étapes)
                        python -m src.etl.pipeline --steps prices risk
Lancement planifié :    DAG Airflow airflow/dags/risk_pipeline_dag.py (appelle les mêmes fonctions)
"""
from __future__ import annotations

import argparse
import time
import uuid
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select

from src import config
from src.collect import ecb, kaggle_fraud, news_rss, stooq
from src.db import schema
from src.db.mongo import get_db, init_mongo
from src.db.postgres import fetch_df, get_engine, init_db, insert_rows, upsert
from src.logging_conf import get_logger
from src.ml.risk import compute_risk_metrics
from src.transform import quality
from src.transform.prices import asset_class, clean_fx, clean_prices
from src.transform.transactions import clean_transactions

log = get_logger(__name__)

STEPS = ["init", "prices", "fx", "transactions", "news", "risk"]


class DataQualityError(RuntimeError):
    pass


def to_rows(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> liste de dict avec types Python natifs (psycopg2 ne gère pas numpy.int64...)."""
    rows = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, np.generic):
                v = v.item()
            if isinstance(v, float) and np.isnan(v):
                v = None
            clean[k] = v
        rows.append(clean)
    return rows


def record_checks(run_id: str, checks: list[dict]) -> None:
    rows = [{k: v for k, v in c.items() if k != "blocking"} | {"run_id": run_id} for c in checks]
    upsert(schema.data_quality_check, rows, ["run_id", "dataset", "check_name"])
    failed = [c for c in checks if not c["passed"]]
    for c in failed:
        log.warning("Contrôle qualité KO : %s/%s (observé=%s)", c["dataset"], c["check_name"], c["observed_value"])
    blocking = [c for c in failed if c["blocking"]]
    if blocking:
        names = ", ".join(f"{c['dataset']}/{c['check_name']}" for c in blocking)
        raise DataQualityError(f"Contrôle(s) bloquant(s) en échec : {names}")


def run_step(run_id: str, step: str, func, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        rows_in, rows_out = func(run_id, *args, **kwargs) or (None, None)
        status, message = "success", None
        return rows_in, rows_out
    except Exception as exc:
        rows_in = rows_out = None
        status, message = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        duration = time.perf_counter() - t0
        try:
            insert_rows(
                schema.etl_run_log,
                [{"run_id": run_id, "step": step, "status": status, "rows_in": rows_in,
                  "rows_out": rows_out, "duration_s": round(duration, 3), "message": message}],
            )
        except Exception:  # le journal ne doit jamais masquer l'erreur d'origine
            log.exception("Impossible d'écrire etl_run_log")
        log.info("[%s] étape %s : %s en %.2f s", run_id[:8], step, status, duration)


# --------------------------------------------------------------------------- étapes
def step_init(run_id: str):
    init_db()
    init_mongo()
    return 0, 0


def _asset_id(ticker: str) -> int:
    upsert(
        schema.dim_asset,
        [{"ticker": ticker, "asset_class": asset_class(ticker), "currency": "USD"}],
        ["ticker"],
    )
    with get_engine().connect() as conn:
        return conn.execute(
            select(schema.dim_asset.c.asset_id).where(schema.dim_asset.c.ticker == ticker)
        ).scalar_one()


def step_prices(run_id: str, tickers: list[str] | None = None, today: date | None = None):
    total_in = total_out = 0
    checks, batches = [], []
    # 1) extraction + transformation + contrôles AVANT tout chargement :
    #    une donnée qui échoue un contrôle bloquant n'entre jamais en base.
    for ticker in tickers or config.TICKERS:
        raw = stooq.fetch_prices(ticker)
        clean = clean_prices(raw)
        checks += quality.check_prices(clean, ticker, today=today)
        total_in += len(raw)
        batches.append((ticker, clean))
    record_checks(run_id, checks)
    # 2) chargement
    for ticker, clean in batches:
        clean.insert(0, "asset_id", _asset_id(ticker))
        total_out += upsert(schema.fact_price, to_rows(clean), ["asset_id", "price_date"])
    return total_in, total_out


def step_fx(run_id: str):
    raw = ecb.fetch_fx()
    clean = clean_fx(raw)
    record_checks(run_id, quality.check_fx(clean))
    return len(raw), upsert(schema.fact_fx_rate, to_rows(clean), ["rate_date", "currency"])


def step_transactions(run_id: str, path=None):
    raw = kaggle_fraud.read_creditcard(path)
    clean, dups = clean_transactions(raw)
    record_checks(run_id, quality.check_transactions(clean, dups))
    return len(raw), upsert(schema.fact_transaction, to_rows(clean), ["transaction_id"])


def step_news(run_id: str, articles: list[dict] | None = None):
    articles = articles if articles is not None else news_rss.fetch_news()
    coll = get_db().news_articles
    written = 0
    for art in articles:
        res = coll.update_one({"link": art["link"]}, {"$set": art}, upsert=True)
        written += int(res.upserted_id is not None or res.modified_count > 0)
    return len(articles), written


def step_risk(run_id: str):
    assets = fetch_df("SELECT asset_id, ticker FROM dim_asset")
    total = 0
    checks = []
    for asset in assets.itertuples():
        prices = fetch_df(
            "SELECT price_date, close FROM fact_price WHERE asset_id = :aid ORDER BY price_date",
            {"aid": int(asset.asset_id)},
        )
        if prices.empty:
            continue
        prices["price_date"] = pd.to_datetime(prices["price_date"]).dt.date
        metrics = compute_risk_metrics(prices)
        checks += quality.check_risk(metrics, asset.ticker)
        metrics.insert(0, "asset_id", int(asset.asset_id))
        total += upsert(schema.risk_metrics, to_rows(metrics), ["asset_id", "metric_date"])
    record_checks(run_id, checks)
    return len(assets), total


STEP_FUNCS = {
    "init": step_init,
    "prices": step_prices,
    "fx": step_fx,
    "transactions": step_transactions,
    "news": step_news,
    "risk": step_risk,
}


def run(steps: list[str] | None = None, run_id: str | None = None) -> str:
    run_id = run_id or str(uuid.uuid4())
    for step in steps or STEPS:
        run_step(run_id, step, STEP_FUNCS[step])
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline ETL gestion des risques")
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    args = parser.parse_args()
    steps = args.steps if "init" in args.steps else ["init", *args.steps]
    run_id = run(steps)
    log.info("Pipeline terminé, run_id=%s", run_id)


if __name__ == "__main__":
    main()
