"""Nettoyage des transactions carte bancaire (dataset Kaggle)."""
from __future__ import annotations

import pandas as pd

V_COLS = [f"v{i}" for i in range(1, 29)]


def clean_transactions(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Retourne (transactions propres, nombre de doublons exacts supprimés).

    - transaction_id = numéro de ligne du fichier source (clé stable => chargement idempotent)
    - suppression des doublons exacts (le dataset en contient ~1 000) : décision documentée
    """
    df = raw.copy()
    df.insert(0, "transaction_id", range(len(df)))
    df = df.rename(columns={"Time": "time_offset_s", "Amount": "amount", "Class": "is_fraud"})
    df = df.rename(columns={f"V{i}": f"v{i}" for i in range(1, 29)})
    feature_cols = ["time_offset_s", *V_COLS, "amount", "is_fraud"]
    before = len(df)
    df = df.dropna(subset=feature_cols)
    df = df[df["amount"] >= 0]
    df = df.drop_duplicates(subset=feature_cols, keep="first")
    duplicates_removed = before - len(df)
    df["is_fraud"] = df["is_fraud"].astype(int).astype(bool)
    return df[["transaction_id", *feature_cols]].reset_index(drop=True), duplicates_removed
