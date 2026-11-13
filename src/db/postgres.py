"""Accès à la base relationnelle : connexion, création du schéma, chargement idempotent (upsert)."""
from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from src import config
from src.db.schema import metadata
from src.logging_conf import get_logger

log = get_logger(__name__)


def database_url() -> str:
    # Lu à l'appel (et non à l'import) pour que les tests puissent pointer vers SQLite.
    return os.getenv("DATABASE_URL", config.DATABASE_URL)


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    # pool_pre_ping : évite les erreurs « connection closed » après une longue inactivité
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    return _engine_for(database_url())


def init_db() -> None:
    """Crée les tables si elles n'existent pas (idempotent)."""
    metadata.create_all(get_engine())
    log.info("Schéma relationnel prêt (%d tables)", len(metadata.tables))


def _insert_for(engine: Engine, table: Table):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"Dialecte non supporté : {engine.dialect.name}")
    return insert(table)


def upsert(
    table: Table,
    rows: Sequence[dict],
    conflict_cols: Iterable[str],
    chunk_size: int = 5000,
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE : relancer le pipeline ne crée jamais de doublons."""
    if not rows:
        return 0
    engine = get_engine()
    conflict_cols = list(conflict_cols)
    columns = list(rows[0].keys())
    update_cols = [c for c in columns if c not in conflict_cols]

    stmt = _insert_for(engine, table)
    if update_cols:
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={c: stmt.excluded[c] for c in update_cols},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)

    with engine.begin() as conn:  # une transaction : tout ou rien
        for start in range(0, len(rows), chunk_size):
            conn.execute(stmt, list(rows[start : start + chunk_size]))
    return len(rows)


def insert_rows(table: Table, rows: Sequence[dict]) -> int:
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(table.insert(), list(rows))
    return len(rows)


def fetch_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Exécute une requête SELECT paramétrée (protection contre l'injection SQL)."""
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        return pd.DataFrame(result.mappings().all())
