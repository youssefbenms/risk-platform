"""Collecte des cours journaliers (OHLCV) depuis Stooq.

Depuis 2026, Stooq exige une clé (`apikey`) pour télécharger les CSV.
Ordre de priorité :
1. API Stooq si STOOQ_APIKEY est renseignée ;
2. sinon, fichier CSV téléchargé à la main dans data/raw/stooq/<ticker>.csv.
Chaque téléchargement est archivé tel quel (couche « raw ») pour la traçabilité.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from src import config
from src.collect.http import make_session
from src.logging_conf import get_logger

log = get_logger(__name__)

STOOQ_URL = "https://stooq.com/q/d/l/"
EXPECTED_COLUMNS = ["Date", "Open", "High", "Low", "Close"]


class StooqError(RuntimeError):
    pass


def raw_path(ticker: str) -> Path:
    safe = ticker.replace("^", "idx_").replace(".", "_")
    return config.DATA_RAW_DIR / "stooq" / f"{safe}.csv"


def _parse(csv_text: str, ticker: str) -> pd.DataFrame:
    if not csv_text.lstrip().startswith("Date"):
        # Stooq renvoie une page texte/HTML (clé manquante, quota dépassé...)
        raise StooqError(f"{ticker} : réponse inattendue de Stooq -> {csv_text[:120]!r}")
    df = pd.read_csv(io.StringIO(csv_text))
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise StooqError(f"{ticker} : colonnes manquantes {missing}")
    return df


def fetch_prices(ticker: str, start: str | None = None) -> pd.DataFrame:
    path = raw_path(ticker)
    if config.STOOQ_APIKEY:
        params = {
            "s": ticker,
            "i": "d",
            "d1": (start or config.PRICE_START_DATE).replace("-", ""),
            "apikey": config.STOOQ_APIKEY,
        }
        resp = make_session().get(STOOQ_URL, params=params, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        df = _parse(resp.text, ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text, encoding="utf-8")
        log.info("Stooq %s : %d lignes téléchargées", ticker, len(df))
        return df
    if path.exists():
        log.warning("STOOQ_APIKEY absente : lecture du fichier local %s", path)
        return _parse(path.read_text(encoding="utf-8"), ticker)
    raise StooqError(
        f"{ticker} : ni STOOQ_APIKEY ni fichier {path}. "
        "Renseigne la clé dans .env ou dépose le CSV à la main."
    )
