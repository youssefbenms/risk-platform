"""Contrôles qualité des données : chaque contrôle produit une ligne tracée en base.

`blocking=True` => si le contrôle échoue, le pipeline s'arrête (la donnée n'est pas fiable).
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def _check(dataset, name, passed, observed=None, threshold=None, details="", blocking=False):
    return {
        "dataset": dataset,
        "check_name": name,
        "passed": bool(passed),
        "observed_value": None if observed is None else float(observed),
        "threshold": None if threshold is None else float(threshold),
        "details": details,
        "blocking": blocking,
    }


def check_prices(df: pd.DataFrame, ticker: str, today: date | None = None) -> list[dict]:
    ds = f"prices:{ticker}"
    checks = [_check(ds, "row_count_min", len(df) >= 30, len(df), 30, "au moins 30 jours", True)]
    if df.empty:
        return checks
    null_rate = df[["open", "high", "low", "close"]].isna().mean().max()
    checks.append(_check(ds, "null_rate_max", null_rate <= 0.01, null_rate, 0.01))
    dups = int(df.duplicated(subset=["price_date"]).sum())
    checks.append(_check(ds, "no_duplicate_dates", dups == 0, dups, 0, blocking=True))
    bad_hl = int((df["high"] < df["low"]).sum())
    checks.append(_check(ds, "high_ge_low", bad_hl == 0, bad_hl, 0))
    jumps = df["close"].pct_change().abs().max()
    checks.append(_check(ds, "max_daily_move", jumps <= 0.5, jumps, 0.5, "variation > 50 % = suspect"))
    today = today or date.today()
    age = (today - max(df["price_date"])).days
    checks.append(_check(ds, "freshness_days", age <= 10, age, 10, "données à jour"))
    return checks


def check_fx(df: pd.DataFrame) -> list[dict]:
    checks = [_check("fx", "row_count_min", len(df) > 0, len(df), 1, blocking=True)]
    if df.empty:
        return checks
    dups = int(df.duplicated(subset=["rate_date", "currency"]).sum())
    checks.append(_check("fx", "no_duplicates", dups == 0, dups, 0, blocking=True))
    checks.append(_check("fx", "positive_rates", (df["rate_per_eur"] > 0).all(), df["rate_per_eur"].min(), 0))
    return checks


def check_transactions(df: pd.DataFrame, duplicates_removed: int) -> list[dict]:
    checks = [_check("transactions", "row_count_min", len(df) >= 1000, len(df), 1000, blocking=True)]
    if df.empty:
        return checks
    fraud_rate = df["is_fraud"].mean()
    checks.append(
        _check("transactions", "fraud_rate_range", 0.0005 <= fraud_rate <= 0.05, fraud_rate, 0.05,
               "taux de fraude attendu ~0,17 %")
    )
    checks.append(_check("transactions", "amount_non_negative", (df["amount"] >= 0).all(), df["amount"].min(), 0))
    checks.append(
        _check("transactions", "duplicates_removed", True, duplicates_removed, None,
               "doublons exacts supprimés (information)")
    )
    null_rate = df.isna().mean().max()
    checks.append(_check("transactions", "null_rate_max", null_rate == 0, null_rate, 0, blocking=True))
    return checks


def check_risk(df: pd.DataFrame, ticker: str) -> list[dict]:
    ds = f"risk:{ticker}"
    if df.empty:
        return [_check(ds, "row_count_min", False, 0, 1, blocking=False)]
    coverage = df["var_95_hist"].notna().mean()
    return [
        _check(ds, "var_coverage", coverage >= 0.5, coverage, 0.5, "part des jours avec VaR calculée"),
        _check(ds, "var_positive", (df["var_95_hist"].dropna() >= 0).all(), df["var_95_hist"].min(), 0),
    ]
