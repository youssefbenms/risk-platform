"""Collecte des taux de change de référence de la BCE (API SDMX du ECB Data Portal).

Série EXR : D.<DEVISE>.EUR.SP00.A = taux journalier, nombre d'unités de devise pour 1 EUR.
"""
from __future__ import annotations

import io

import pandas as pd

from src import config
from src.collect.http import make_session
from src.logging_conf import get_logger

log = get_logger(__name__)

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"


def fetch_fx(currencies: list[str] | None = None, start: str | None = None) -> pd.DataFrame:
    currencies = currencies or config.FX_CURRENCIES
    url = ECB_URL.format(currencies="+".join(currencies))
    params = {"format": "csvdata", "startPeriod": start or config.PRICE_START_DATE}
    resp = make_session().get(url, params=params, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    path = config.DATA_RAW_DIR / "ecb" / "exr.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(resp.text, encoding="utf-8")
    log.info("BCE : %d observations de change pour %s", len(df), currencies)
    return df[["CURRENCY", "TIME_PERIOD", "OBS_VALUE"]]
