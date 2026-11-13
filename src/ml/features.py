"""Construction des variables du modèle de fraude — partagée entre l'entraînement et l'API
pour garantir exactement le même traitement en production (pas de « training/serving skew »)."""
from __future__ import annotations

import numpy as np
import pandas as pd

V_COLS = [f"v{i}" for i in range(1, 29)]
FEATURES = [*V_COLS, "amount_log", "hour"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df[V_COLS].astype(float).copy()
    out["amount_log"] = np.log1p(df["amount"].astype(float))
    # Time = secondes depuis la 1re transaction du dataset -> heure de la journée
    out["hour"] = (df["time_offset_s"].astype(float) // 3600) % 24
    return out[FEATURES]
