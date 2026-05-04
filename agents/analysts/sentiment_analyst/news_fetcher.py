"""
agents/sentiment_analyst/news_fetcher.py — Collecte de news financières
Source 1 : NewsAPI (si clé dans .env) — sinon flux RSS Yahoo Finance
"""

import sys
import os
import requests
import re
from xml.etree import ElementTree as ET
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import config
from utils.logger import get_logger

logger = get_logger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# RSS Yahoo Finance par ticker — fallback gratuit sans clé
YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"

# Mots-clés sensibles pour la classification d'impact
MOTS_POSITIFS = ["surges", "rally", "beats", "record", "upgrade", "bullish", "growth",
                 "strong", "breakout", "hits", "outperform", "bénéfices", "hausse"]
MOTS_NEGATIFS = ["plunges", "crashes", "misses", "downgrade", "bearish", "recession",
                 "falls", "drops", "warning", "cuts", "chute", "baisse", "récession"]


def classer_impact(titre: str) -> str:
    """Classe l'impact d'une news en : positif / négatif / neutre."""
    titre_bas = titre.lower()
    score_pos = sum(1 for m in MOTS_POSITIFS if m in titre_bas)
    score_neg = sum(1 for m in MOTS_NEGATIFS if m in titre_bas)
    if score_pos > score_neg: return "positif"
    if score_neg > score_pos: return "négatif"
    return "neutre"


def recuperer_news_newsapi(requete: str, nb_max: int = 5) -> list[dict]:
    """Récupère des news via NewsAPI (nécessite clé dans .env)."""
    if not config.NEWSAPI_KEY:
        return []
    try:
        params = {
            "q":         requete,
            "language":  "en",
            "sortBy":    "publishedAt",
            "pageSize":  nb_max,
            "apiKey":    config.NEWSAPI_KEY,
        }
        r = requests.get(NEWSAPI_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        articles = data.get("articles", [])
        return [{
            "titre":       a.get("title", ""),
            "source":      a.get("source", {}).get("name", ""),
            "publie_le":   a.get("publishedAt", ""),
            "impact":      classer_impact(a.get("title", "")),
        } for a in articles]
    except Exception as e:
        logger.error(f"Erreur NewsAPI : {e}")
        return []


def recuperer_news_yahoo_rss(ticker: str, nb_max: int = 5) -> list[dict]:
    """
    Fallback : news via RSS Yahoo Finance (gratuit, sans clé).
    Parse le XML pour extraire titre, date, source.
    """
    try:
        params = {"s": ticker, "region": "US", "lang": "en-US"}
        r = requests.get(YAHOO_RSS_URL, params=params, timeout=15)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        articles = []
        for item in root.findall(".//item")[:nb_max]:
            titre = item.findtext("title", "")
            articles.append({
                "titre":     titre,
                "source":    "Yahoo Finance",
                "publie_le": item.findtext("pubDate", ""),
                "impact":    classer_impact(titre),
            })
        return articles
    except Exception as e:
        logger.error(f"Erreur Yahoo RSS {ticker} : {e}")
        return []


def recuperer_news(ticker_ou_requete: str, nb_max: int = 5) -> list[dict]:
    """Essaie NewsAPI d'abord, RSS Yahoo en fallback."""
    news = recuperer_news_newsapi(ticker_ou_requete, nb_max)
    if news:
        return news
    # Fallback RSS — fonctionne avec un ticker (BTC-USD, AAPL, etc.)
    return recuperer_news_yahoo_rss(ticker_ou_requete, nb_max)


def resume_news(ticker_ou_requete: str, nb_max: int = 5) -> str:
    """Génère un résumé textuel des news pour un actif."""
    news = recuperer_news(ticker_ou_requete, nb_max)
    if not news:
        return "  Aucune news disponible"

    lignes = []
    for n in news:
        titre = n["titre"][:100] + "..." if len(n["titre"]) > 100 else n["titre"]
        lignes.append(f"  • [{n['impact']}] {titre}")
    return "\n".join(lignes)
