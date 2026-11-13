"""Collecte de données NON structurées : communiqués et discours de la BCE.

1. Lecture du flux RSS (XML) avec BeautifulSoup ;
2. Scraping du texte des pages HTML des derniers articles (BeautifulSoup).
Source institutionnelle publique, aucune donnée personnelle collectée (RGPD) ;
requêtes espacées (délai) pour ne pas surcharger le site.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from src import config
from src.collect.http import make_session
from src.logging_conf import get_logger

log = get_logger(__name__)


def parse_rss(xml_text: str) -> list[dict]:
    soup = BeautifulSoup(xml_text, "xml")
    articles = []
    for item in soup.find_all("item"):
        link = (item.link.get_text(strip=True) if item.link else "").replace("//press", "/press")
        if not link:
            continue
        pub = item.pubDate.get_text(strip=True) if item.pubDate else None
        try:
            published = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            published = None
        articles.append(
            {
                "source": "ECB",
                "title": item.title.get_text(strip=True) if item.title else "",
                "link": link,
                "published_at": published.astimezone(UTC) if published else None,
                "summary": item.description.get_text(strip=True) if item.description else None,
            }
        )
    return articles


def extract_text(html: str, max_chars: int = 20000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.body or soup
    text = " ".join(main.get_text(" ", strip=True).split())
    return text[:max_chars]


def fetch_news(fetch_body: bool = True, max_bodies: int = 10, delay_s: float = 1.0) -> list[dict]:
    session = make_session()
    resp = session.get(config.ECB_RSS_URL, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    articles = parse_rss(resp.text)
    now = datetime.now(UTC)
    for i, art in enumerate(articles):
        art["ingested_at"] = now
        art["body"] = None
        if fetch_body and i < max_bodies and art["link"].endswith(".html"):
            try:
                page = session.get(art["link"], timeout=config.HTTP_TIMEOUT)
                page.raise_for_status()
                art["body"] = extract_text(page.text)
            except Exception as exc:  # un article en échec ne bloque pas le flux
                log.warning("Scraping impossible pour %s : %s", art["link"], exc)
            time.sleep(delay_s)
    log.info("BCE RSS : %d articles collectés", len(articles))
    return articles
