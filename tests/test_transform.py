import pandas as pd

from src.transform.prices import asset_class, clean_fx, clean_prices
from src.transform.transactions import clean_transactions
from tests.conftest import make_creditcard, make_fx, make_prices


def test_clean_prices_removes_bad_rows():
    raw = make_prices(50)
    raw = pd.concat([raw, raw.iloc[[0]]])          # doublon de date
    raw.loc[len(raw)] = ["2026-11-11", -1, 1, 1, 1, 10]  # prix négatif
    raw.loc[len(raw)] = ["2026-11-12", 10, 5, 8, 9, 10]  # high < low
    raw.loc[len(raw)] = ["pas-une-date", 1, 2, 1, 1, 1]
    clean = clean_prices(raw)
    assert len(clean) == 50
    assert clean["price_date"].is_monotonic_increasing
    assert (clean["high"] >= clean["low"]).all()
    assert list(clean.columns) == ["price_date", "open", "high", "low", "close", "volume"]


def test_clean_prices_without_volume_column():
    raw = make_prices(10).drop(columns="Volume")
    assert clean_prices(raw)["volume"].isna().all()


def test_clean_fx():
    raw = pd.concat([make_fx(), make_fx().iloc[[0]]])
    clean = clean_fx(raw)
    assert len(clean) == 60
    assert set(clean["currency"]) == {"USD", "GBP"}


def test_clean_transactions_dedup_and_types():
    raw = make_creditcard(1000)
    raw = pd.concat([raw, raw.iloc[[0, 1]]], ignore_index=True)
    clean, dups = clean_transactions(raw)
    assert dups == 2
    assert len(clean) == 1000
    assert clean["is_fraud"].dtype == bool
    assert clean["transaction_id"].is_unique


def test_asset_class():
    assert asset_class("^spx") == "index"
    assert asset_class("aapl.us") == "equity"
