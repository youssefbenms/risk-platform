"""DAGs Airflow de la plateforme de gestion des risques.

1. market_risk_daily  : chaque jour ouvré à 07:00 (Paris)
       init -> [prices, fx, news] -> risk
   Les 3 collectes sont indépendantes et tournent en parallèle ; risk attend les prix.
2. fraud_model_training : déclenché à la main (bouton ▶ dans l'interface)
       init -> transactions -> train
Les tâches appellent exactement les mêmes fonctions que la ligne de commande
(python -m src.etl.pipeline) : un seul code, testé en CI.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task  # API publique d'Airflow 3

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=30),
}


def _run(step: str) -> None:
    from src.etl import pipeline  # import tardif : le scheduler parse le DAG sans charger pandas

    run_id = get_current_context()["run_id"]
    pipeline.run_step(run_id, step, pipeline.STEP_FUNCS[step])


@dag(
    dag_id="market_risk_daily",
    schedule="0 7 * * 1-5",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["risque", "etl"],
    doc_md=__doc__,
)
def market_risk_daily():
    @task
    def init():
        _run("init")

    @task
    def prices():
        _run("prices")

    @task
    def fx():
        _run("fx")

    @task
    def news():
        _run("news")

    @task
    def risk():
        _run("risk")

    p = prices()
    init() >> [p, fx(), news()]
    p >> risk()


@dag(
    dag_id="fraud_model_training",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    catchup=False,
    default_args=DEFAULT_ARGS | {"execution_timeout": timedelta(hours=1)},
    tags=["fraude", "ia"],
)
def fraud_model_training():
    @task
    def init():
        _run("init")

    @task
    def transactions():
        _run("transactions")

    @task
    def train():
        from src.db.postgres import fetch_df
        from src.ml.fraud_train import train as train_model

        metrics = train_model(fetch_df("SELECT * FROM fact_transaction ORDER BY transaction_id"))
        return metrics["test"]  # visible dans l'onglet XCom

    init() >> transactions() >> train()


market_risk_daily()
fraud_model_training()
