"""Gestion proactive du risque de marché.

1. Indicateurs statistiques classiques (réglementation bancaire / Bâle) :
   - rendement logarithmique journalier
   - volatilité glissante 20 jours, annualisée (×√252)
   - VaR historique 95 % et 99 % à 1 jour sur 250 jours glissants
   - VaR paramétrique (gaussienne) 95 %
   VaR exprimée en perte positive : 0,03 = « on ne perd pas plus de 3 % en 1 jour dans 95 % des cas ».
2. Détection d'anomalies NON SUPERVISÉE (Isolation Forest) : signale les journées de marché
   atypiques (krach, choc de volatilité) sans avoir besoin d'étiquettes.
   Modèle léger (CPU, < 1 s) : choix frugal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

Z_95 = 1.6448536269514722  # quantile 95 % de la loi normale
WINDOW_VAR = 250
WINDOW_VOL = 20


def compute_risk_metrics(prices: pd.DataFrame, contamination: float = 0.01) -> pd.DataFrame:
    """`prices` doit contenir price_date et close, triés ou non."""
    df = prices[["price_date", "close"]].sort_values("price_date").reset_index(drop=True)
    out = pd.DataFrame({"metric_date": df["price_date"]})
    ret = np.log(df["close"]).diff()
    out["log_return"] = ret
    out["vol_20d_ann"] = ret.rolling(WINDOW_VOL, min_periods=WINDOW_VOL).std() * np.sqrt(252)

    roll = ret.rolling(WINDOW_VAR, min_periods=60)  # au moins ~3 mois d'historique
    out["var_95_hist"] = -roll.quantile(0.05)
    out["var_99_hist"] = -roll.quantile(0.01)
    out["var_95_param"] = Z_95 * roll.std() - roll.mean()

    out["anomaly_score"] = np.nan
    out["is_anomaly"] = pd.Series([None] * len(out), dtype=object)
    feats = pd.DataFrame(
        {"ret": ret, "abs_ret": ret.abs(), "vol": out["vol_20d_ann"]}
    ).dropna()
    if len(feats) >= 50:
        model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
        model.fit(feats)
        # score_samples : plus c'est bas, plus c'est anormal -> on inverse pour lire « plus haut = plus risqué »
        out.loc[feats.index, "anomaly_score"] = -model.score_samples(feats)
        out.loc[feats.index, "is_anomaly"] = model.predict(feats) == -1

    out = out.iloc[1:].reset_index(drop=True)  # 1re ligne sans rendement
    return out.replace({np.nan: None})
