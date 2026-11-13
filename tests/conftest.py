"""Configuration des tests : SQLite + mongomock -> aucun serveur nécessaire (CI GitHub Actions)."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="risk-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["MONGO_URL"] = "mongomock://"
os.environ["API_KEY"] = "test-key"
os.environ["MODELS_DIR"] = str(_TMP / "models")
os.environ["DATA_RAW_DIR"] = str(_TMP / "raw")
os.environ["STOOQ_APIKEY"] = ""

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


def make_prices(n: int = 400, seed: int = 0, end: str = "2026-11-10") -> pd.DataFrame:
    """Marche aléatoire géométrique au format brut Stooq."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    close[n // 2] *= 0.85  # un choc pour que l'Isolation Forest ait quelque chose à voir
    return pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close * 0.999, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": rng.integers(1e5, 1e6, n),
    })


def make_creditcard(n: int = 6000, fraud_rate: float = 0.02, seed: int = 0) -> pd.DataFrame:
    """Dataset au format Kaggle ; les fraudes sont décalées sur quelques composantes."""
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < fraud_rate).astype(int)
    v = rng.normal(0, 1, (n, 28))
    v[y == 1, :4] += 3.0
    df = pd.DataFrame(v, columns=[f"V{i}" for i in range(1, 29)])
    df.insert(0, "Time", np.sort(rng.uniform(0, 172800, n)))
    df["Amount"] = np.round(rng.exponential(80, n), 2)
    df["Class"] = y
    return df


def make_fx() -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-11-10", periods=30).strftime("%Y-%m-%d")
    rows = [{"CURRENCY": c, "TIME_PERIOD": d, "OBS_VALUE": r}
            for c, r in [("USD", 1.10), ("GBP", 0.86)] for d in dates]
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def tmp_dir() -> Path:
    return _TMP
