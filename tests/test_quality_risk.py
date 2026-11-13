from datetime import date

import pandas as pd

from src.ml.risk import compute_risk_metrics
from src.transform import quality
from src.transform.prices import clean_prices
from tests.conftest import make_prices


def test_price_checks_pass_on_clean_data():
    df = clean_prices(make_prices(100))
    checks = quality.check_prices(df, "aapl.us", today=date(2026, 11, 12))
    failed = [c["check_name"] for c in checks if not c["passed"]]
    assert failed == []


def test_price_checks_block_on_empty():
    checks = quality.check_prices(clean_prices(make_prices(5)), "x", today=date(2026, 11, 12))
    assert any(c["blocking"] and not c["passed"] for c in checks)


def test_freshness_fails_on_old_data():
    df = clean_prices(make_prices(100, end="2025-01-10"))
    checks = {c["check_name"]: c for c in quality.check_prices(df, "x", today=date(2026, 11, 12))}
    assert not checks["freshness_days"]["passed"]


def test_risk_metrics():
    prices = clean_prices(make_prices(400))
    m = compute_risk_metrics(prices)
    assert len(m) == 399
    var = pd.Series([v for v in m["var_95_hist"] if v is not None])
    assert len(var) > 300 and (var > 0).all()
    var99 = pd.Series([v for v in m["var_99_hist"] if v is not None])
    assert var99.mean() >= var.mean()          # VaR 99 % >= VaR 95 %
    flags = [f for f in m["is_anomaly"] if f is not None]
    assert 0 < sum(flags) <= 0.05 * len(flags)
