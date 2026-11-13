"""Configuration centrale : toutes les valeurs viennent des variables d'environnement (.env).

Aucun secret n'est écrit en dur dans le code (exigence sécurité C7 / C13 / C15).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")  # sans effet si le fichier n'existe pas (ex. en CI)


def _get(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


# --- Bases de données -------------------------------------------------------
DATABASE_URL = _get(
    "DATABASE_URL", "postgresql+psycopg2://risk:risk@localhost:5432/riskdb"
)
MONGO_URL = _get("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = _get("MONGO_DB", "riskdb")

# --- Sources de données -----------------------------------------------------
STOOQ_APIKEY = _get("STOOQ_APIKEY")
# Tickers Stooq suivis (actions US + indice) — modifiable sans toucher au code
TICKERS = [t.strip() for t in _get("TICKERS", "aapl.us,msft.us,jpm.us,gs.us,^spx").split(",") if t.strip()]
FX_CURRENCIES = [c.strip() for c in _get("FX_CURRENCIES", "USD,GBP,JPY,CHF").split(",") if c.strip()]
PRICE_START_DATE = _get("PRICE_START_DATE", "2018-01-01")
ECB_RSS_URL = _get("ECB_RSS_URL", "https://www.ecb.europa.eu/rss/press.xml")

# --- Fichiers ----------------------------------------------------------------
DATA_RAW_DIR = Path(_get("DATA_RAW_DIR", str(ROOT_DIR / "data" / "raw")))
MODELS_DIR = Path(_get("MODELS_DIR", str(ROOT_DIR / "models")))
FRAUD_CSV = DATA_RAW_DIR / "creditcard.csv"

# --- API ---------------------------------------------------------------------
API_KEY = _get("API_KEY", "change-me")

# --- Réseau ------------------------------------------------------------------
HTTP_TIMEOUT = int(_get("HTTP_TIMEOUT", "30"))
USER_AGENT = "risk-platform/1.0 (projet pédagogique Data Engineer)"
