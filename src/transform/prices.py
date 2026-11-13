"""Nettoyage / normalisation des cours (Stooq) et des taux de change (BCE)."""
from __future__ import annotations

import pandas as pd

OHLC = ["open", "high", "low", "close"]


def clean_prices(raw: pd.DataFrame) -> pd.DataFrame:
    """Formatage, typage, déduplication et règles métier sur les cours OHLCV."""
    df = raw.rename(columns=str.lower).copy()
    if "volume" not in df.columns:  # les indices n'ont pas toujours de volume
        df["volume"] = None
    df["price_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for col in [*OHLC, "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["price_date", *OHLC])
    df = df[(df[OHLC] > 0).all(axis=1)]                 # un prix est toujours > 0
    df = df[df["high"] >= df["low"]]                     # cohérence haut/bas
    df = df.drop_duplicates(subset=["price_date"], keep="last")
    df = df.sort_values("price_date").reset_index(drop=True)
    return df[["price_date", *OHLC, "volume"]]


def clean_fx(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(
        columns={"CURRENCY": "currency", "TIME_PERIOD": "rate_date", "OBS_VALUE": "rate_per_eur"}
    ).copy()
    df["rate_date"] = pd.to_datetime(df["rate_date"], errors="coerce").dt.date
    df["rate_per_eur"] = pd.to_numeric(df["rate_per_eur"], errors="coerce")
    df["currency"] = df["currency"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["rate_date", "rate_per_eur"])
    df = df[df["rate_per_eur"] > 0]
    df = df.drop_duplicates(subset=["rate_date", "currency"], keep="last")
    return df.sort_values(["currency", "rate_date"]).reset_index(drop=True)[
        ["rate_date", "currency", "rate_per_eur"]
    ]


def asset_class(ticker: str) -> str:
    return "index" if ticker.startswith("^") else "equity"
