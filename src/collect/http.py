"""Session HTTP commune : timeout, User-Agent explicite et retries avec backoff exponentiel."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1.0,  # 1 s, 2 s, 4 s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session
