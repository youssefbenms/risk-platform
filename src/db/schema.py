"""Modèle de données relationnel (PostgreSQL) — source unique de vérité du schéma.

Schéma en étoile simplifié :
- dim_asset            : référentiel des actifs (donnée de référence)
- fact_price           : cours journaliers OHLCV (Stooq)
- fact_fx_rate         : taux de change de référence BCE (EUR -> devise)
- fact_transaction     : transactions carte bancaire anonymisées (Kaggle, PCA)
- risk_metrics         : indicateurs de risque calculés (rendement, volatilité, VaR, anomalie)
- data_quality_check   : résultats des contrôles qualité à chaque exécution
- etl_run_log          : journal des exécutions du pipeline (traçabilité / audit)

Compatible SQLAlchemy 1.4 (image Airflow) et 2.0 (API).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

dim_asset = Table(
    "dim_asset",
    metadata,
    Column("asset_id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", String(20), nullable=False, unique=True),
    Column("asset_class", String(20), nullable=False),  # equity | index
    Column("currency", String(3), nullable=False, server_default="USD"),
    Column("created_at", DateTime, server_default=func.now()),
)

fact_price = Table(
    "fact_price",
    metadata,
    Column("asset_id", Integer, ForeignKey("dim_asset.asset_id"), primary_key=True),
    Column("price_date", Date, primary_key=True),
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
    Column("volume", Float),
    Column("loaded_at", DateTime, server_default=func.now()),
)

fact_fx_rate = Table(
    "fact_fx_rate",
    metadata,
    Column("rate_date", Date, primary_key=True),
    Column("currency", String(3), primary_key=True),
    Column("rate_per_eur", Float, nullable=False),
    Column("loaded_at", DateTime, server_default=func.now()),
)

# Les colonnes V1..V28 sont des composantes PCA : aucune donnée personnelle (RGPD).
_v_columns = [Column(f"v{i}", Float, nullable=False) for i in range(1, 29)]
fact_transaction = Table(
    "fact_transaction",
    metadata,
    Column("transaction_id", BigInteger, primary_key=True),  # n° de ligne du fichier source
    Column("time_offset_s", Float, nullable=False),
    *_v_columns,
    Column("amount", Float, nullable=False),
    Column("is_fraud", Boolean, nullable=False),
    Column("loaded_at", DateTime, server_default=func.now()),
)

risk_metrics = Table(
    "risk_metrics",
    metadata,
    Column("asset_id", Integer, ForeignKey("dim_asset.asset_id"), primary_key=True),
    Column("metric_date", Date, primary_key=True),
    Column("log_return", Float),
    Column("vol_20d_ann", Float),
    Column("var_95_hist", Float),
    Column("var_99_hist", Float),
    Column("var_95_param", Float),
    Column("anomaly_score", Float),
    Column("is_anomaly", Boolean),
    Column("computed_at", DateTime, server_default=func.now()),
)

data_quality_check = Table(
    "data_quality_check",
    metadata,
    Column("check_id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(250), nullable=False),
    Column("dataset", String(50), nullable=False),
    Column("check_name", String(80), nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("observed_value", Float),
    Column("threshold", Float),
    Column("details", Text),
    Column("checked_at", DateTime, server_default=func.now()),
    UniqueConstraint("run_id", "dataset", "check_name", name="uq_quality_run_check"),
)

etl_run_log = Table(
    "etl_run_log",
    metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(250), nullable=False),
    Column("step", String(50), nullable=False),
    Column("status", String(10), nullable=False),  # success | failed
    Column("rows_in", Integer),
    Column("rows_out", Integer),
    Column("duration_s", Float),
    Column("message", Text),
    Column("logged_at", DateTime, server_default=func.now()),
)
