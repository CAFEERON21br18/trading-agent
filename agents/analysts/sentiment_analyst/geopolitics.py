"""
agents/analysts/sentiment_analyst/geopolitics.py — Veille géopolitique
Classifie les news en catégories d'événements et retourne l'impact sectoriel suggéré.
Utilisé par les explorateurs pour orienter leurs scans.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger
from utils.cache import avec_cache
from agents.analysts.sentiment_analyst.news_fetcher import recuperer_news_newsapi

logger = get_logger(__name__)

# ── Catégories d'événements et mots-clés ─────────────────────────────────────
CATEGORIES = {
    "CONFLIT_MILITAIRE": {
        "mots_cles": ["war", "guerre", "conflict", "invasion", "missile", "military strike",
                      "troops", "battle", "ceasefire", "armed forces"],
        "secteurs_haussiers": ["défense", "énergie", "or", "armement"],
        "secteurs_baissiers": ["tourisme", "luxe"],
        "actifs_recommandes": ["GC=F", "CL=F", "BZ=F", "RTX", "LMT", "NOC", "BA"],
    },
    "CRISE_BANCAIRE": {
        "mots_cles": ["bank failure", "bailout", "banking crisis", "bank run",
                      "credit crunch", "insolvency", "default sovereign"],
        "secteurs_haussiers": ["or", "valeur refuge", "obligations"],
        "secteurs_baissiers": ["financières", "immobilier"],
        "actifs_recommandes": ["GC=F", "TLT", "JPM", "GS", "BAC"],
    },
    "REGULATION_CRYPTO": {
        "mots_cles": ["sec crypto", "crypto ban", "crypto regulation", "bitcoin etf",
                      "stablecoin law", "mica", "crypto law"],
        "secteurs_haussiers": [],  # peut être positif OU négatif selon le contenu
        "secteurs_baissiers": [],
        "actifs_recommandes": ["BTC-USD", "ETH-USD", "SOL-USD"],
    },
    "ELECTION_MAJEURE": {
        "mots_cles": ["election", "presidential", "polls", "vote", "campaign",
                      "candidate", "incumbent"],
        "secteurs_haussiers": [],
        "secteurs_baissiers": [],
        "actifs_recommandes": [],  # dépend du pays
    },
    "CATASTROPHE_NATURELLE": {
        "mots_cles": ["earthquake", "hurricane", "flood", "wildfire", "tsunami",
                      "tornado", "natural disaster", "typhoon"],
        "secteurs_haussiers": ["assurances", "matériaux de construction", "reconstruction"],
        "secteurs_baissiers": ["tourisme", "agriculture régionale"],
        "actifs_recommandes": [],
    },
    "SANCTIONS": {
        "mots_cles": ["sanctions", "embargo", "trade ban", "asset freeze", "blacklist"],
        "secteurs_haussiers": ["défense", "énergie alternative"],
        "secteurs_baissiers": ["matières premières du pays sanctionné"],
        "actifs_recommandes": [],
    },
    "DECISION_BANQUE_CENTRALE": {
        "mots_cles": ["fed rate", "ecb", "interest rate", "rate hike", "rate cut",
                      "fomc", "powell", "lagarde", "bank of japan", "boe", "snb"],
        "secteurs_haussiers": ["dépend de la direction"],
        "secteurs_baissiers": [],
        "actifs_recommandes": ["TLT", "EURUSD=X", "GBPUSD=X", "USDJPY=X"],
    },
    "PANDEMIE": {
        "mots_cles": ["pandemic", "epidemic", "outbreak", "lockdown", "covid", "virus"],
        "secteurs_haussiers": ["santé", "tech", "pharma"],
        "secteurs_baissiers": ["tourisme", "aérien", "luxe"],
        "actifs_recommandes": ["PFE", "MRNA", "ZM", "AMZN"],
    },
}


def _classifier_titre(titre: str) -> list[str]:
    """Retourne la liste des catégories matchées par le titre."""
    titre_bas = (titre or "").lower()
    matches = []
    for cat, data in CATEGORIES.items():
        if any(m in titre_bas for m in data["mots_cles"]):
            matches.append(cat)
    return matches


def detecter_evenements(nb_news: int = 30) -> list[dict]:
    """
    Récupère les news macro-globales et classe celles qui matchent une catégorie.
    Cache 1h via TTL geopolitique.
    """
    def fetch():
        # Requêtes larges pour capter le contexte global
        requetes = ["geopolitics", "central bank", "war", "sanctions", "election"]
        articles = []
        for req in requetes:
            try:
                articles.extend(recuperer_news_newsapi(req, nb_max=nb_news // len(requetes) + 1))
            except Exception as e:
                logger.error(f"News géopolitique '{req}' : {e}")
        # Classification
        evenements = []
        deja_vu = set()
        for a in articles:
            titre = a.get("titre", "")
            if titre in deja_vu:
                continue
            deja_vu.add(titre)
            cats = _classifier_titre(titre)
            if cats:
                for cat in cats:
                    evenements.append({
                        "categorie":          cat,
                        "titre":              titre[:200],
                        "source":             a.get("source", ""),
                        "publie_le":          a.get("publie_le", ""),
                        "secteurs_haussiers": CATEGORIES[cat]["secteurs_haussiers"],
                        "secteurs_baissiers": CATEGORIES[cat]["secteurs_baissiers"],
                        "actifs_recommandes": CATEGORIES[cat]["actifs_recommandes"],
                    })
        return evenements

    return avec_cache("geopolitique", "global", fetch) or []


def resume_contexte_geopolitique(nb_news: int = 30) -> dict:
    """
    Synthèse du contexte géopolitique : catégories actives + actifs à surveiller.
    """
    evenements = detecter_evenements(nb_news)
    if not evenements:
        return {"actif": False, "categories": [], "actifs_a_surveiller": [], "evenements": []}

    categories = {}
    actifs = set()
    for e in evenements:
        categories[e["categorie"]] = categories.get(e["categorie"], 0) + 1
        actifs.update(e["actifs_recommandes"])

    return {
        "actif":               True,
        "categories":          categories,  # {CONFLIT_MILITAIRE: 3, ...}
        "actifs_a_surveiller": sorted(actifs),
        "evenements":          evenements[:10],  # top 10 pour le rapport
    }
