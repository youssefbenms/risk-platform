"""Lecture du dataset Kaggle « Credit Card Fraud Detection » (fichier creditcard.csv).

Le fichier est téléchargé manuellement depuis Kaggle (licence ODbL) puis déposé dans data/raw/.
Les variables V1..V28 sont déjà anonymisées par ACP : aucune donnée personnelle directe.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config
from src.logging_conf import get_logger

log = get_logger(__name__)

EXPECTED = ["Time", *[f"V{i}" for i in range(1, 29)], "Amount", "Class"]


def read_creditcard(path: Path | None = None) -> pd.DataFrame:
    path = Path(path or config.FRAUD_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} introuvable : télécharge creditcard.csv depuis Kaggle "
            "(mlg-ulb/creditcardfraud) et place-le dans data/raw/."
        )
    df = pd.read_csv(path)
    missing = [c for c in EXPECTED if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path.name} : {missing}")
    log.info("Kaggle fraude : %d transactions lues", len(df))
    return df
