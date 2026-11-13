"""Accès à MongoDB (NoSQL) : données non structurées (actualités) et journaux de prédiction.

MONGO_URL="mongomock://" permet aux tests de tourner sans serveur MongoDB.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING

from src import config


@lru_cache(maxsize=2)
def _client_for(url: str):
    if url.startswith("mongomock://"):
        import mongomock  # dépendance de test uniquement

        return mongomock.MongoClient()
    from pymongo import MongoClient

    return MongoClient(url, serverSelectionTimeoutMS=5000)


def get_db():
    url = os.getenv("MONGO_URL", config.MONGO_URL)
    name = os.getenv("MONGO_DB", config.MONGO_DB)
    return _client_for(url)[name]


def init_mongo() -> None:
    """Index : unicité des articles (pas de doublon) + tri rapide par date."""
    db = get_db()
    db.news_articles.create_index([("link", ASCENDING)], unique=True)
    db.news_articles.create_index([("published_at", DESCENDING)])
    db.prediction_logs.create_index([("created_at", DESCENDING)])
