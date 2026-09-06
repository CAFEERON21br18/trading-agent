"""
agents/technical_skills/news_catalyst.py — Skill 7 : détection de catalyseurs news.

Scanne les titres de news pour repérer un événement majeur qui doit
déclencher une analyse hors-cycle (au lieu d'attendre le prochain cycle).

Le cache news (utils/cache TTL 30min) est déjà mis à jour dans news_fetcher
(v5.5.6) → réduit drastiquement les 429 NewsAPI/Yahoo RSS.

Python pur, aucun LLM.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from agents.analysts.sentiment_analyst.news_fetcher import recuperer_news

logger = get_logger(__name__)

# ── Mots-clés catalyseurs à HAUTE sévérité (news majeure = ré-analyse immédiate)
MOTS_HAUT = [
    "earnings beat", "earnings miss", "earnings surprise", "guidance", "warns",
    "acquisition", "acquires", "buyout", "merger",
    "sec charges", "sec sues", "sec fine", "lawsuit",
    "hack", "hacked", "exploit", "breach",
    "fda approval", "fda rejection", "phase 3",
    "bankruptcy", "insolvency", "chapter 11", "default",
    "recall", "product recall",
    "ceo resigns", "ceo fired", "ceo steps down",
    "delisting", "halted", "trading halt",
    "regulatory approval", "sec approval", "etf approval",
]

# ── Mots-clés MOYENS (à surveiller sans déclencher forcément)
MOTS_MOYEN = [
    "upgrade", "downgrade", "raised", "lowered",
    "partnership", "collaboration", "deal",
    "launch", "unveil", "announces",
    "beats estimates", "misses estimates",
    "buyback", "dividend", "split",
    "expansion", "new market", "restructuring",
]


def _classe(titre: str) -> tuple[str, str] | None:
    """Retourne (severite, mot_matché) ou None si aucun catalyseur."""
    t = (titre or "").lower()
    for m in MOTS_HAUT:
        if m in t:
            return ("haute", m)
    for m in MOTS_MOYEN:
        if m in t:
            return ("moyenne", m)
    return None


def detecter_catalyseurs(news_list: list[dict]) -> list[dict]:
    """Retourne les catalyseurs détectés dans une liste de news.
    [{titre, severite, mot_match, impact, source, publie_le}]"""
    out = []
    for n in news_list or []:
        titre = n.get("titre", "")
        c = _classe(titre)
        if c is None:
            continue
        out.append({
            "titre":     titre[:200],
            "severite":  c[0],
            "mot_match": c[1],
            "impact":    n.get("impact", "neutre"),
            "source":    n.get("source", ""),
            "publie_le": n.get("publie_le", ""),
        })
    return out


def catalyseurs_actif(ticker: str, nb_max: int = 5) -> list[dict]:
    """Récupère (via cache) les news d'un actif et détecte les catalyseurs."""
    news = recuperer_news(ticker, nb_max)
    return detecter_catalyseurs(news)


def scanner_watchlist(tickers: list[str], nb_par_actif: int = 3) -> dict:
    """Scan de la watchlist. Retourne {ticker: [catalyseurs]} pour les
    actifs ayant AU MOINS UN catalyseur. Utilise le cache news (30min)."""
    out: dict = {}
    for t in tickers[:20]:  # limite dure pour éviter la surcharge
        try:
            cats = catalyseurs_actif(t, nb_par_actif)
        except Exception as e:
            logger.warning(f"scanner_watchlist({t}) : {e}")
            cats = []
        if cats:
            out[t] = cats
    return out


def catalyseurs_hauts(scan: dict) -> dict:
    """Filtre : ne garde que les actifs avec au moins 1 catalyseur haute sévérité."""
    return {t: [c for c in cats if c["severite"] == "haute"]
            for t, cats in scan.items()
            if any(c["severite"] == "haute" for c in cats)}
