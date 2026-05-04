"""
utils/helpers.py — Fonctions utilitaires partagées entre tous les modules
"""

import json
import os
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_FILE = os.path.join(BASE_DIR, "data", "watchlist.json")


def charger_watchlist() -> dict:
    """
    Charge la watchlist depuis data/watchlist.json.
    Retourne uniquement les actifs avec "actif": true.
    """
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        watchlist = {}
        for categorie, actifs in data.items():
            # Ignorer les clés de commentaires
            if categorie.startswith("_"):
                continue
            watchlist[categorie] = {
                ticker: info for ticker, info in actifs.items()
                if info.get("actif", True)
            }

        total = sum(len(v) for v in watchlist.values())
        logger.info(f"Watchlist chargée : {total} actifs actifs.")
        return watchlist

    except FileNotFoundError:
        logger.error(f"Fichier watchlist introuvable : {WATCHLIST_FILE}")
        return {}
    except Exception as e:
        logger.error(f"Erreur chargement watchlist : {e}")
        return {}


def tous_les_tickers(watchlist: dict) -> list:
    """Retourne la liste à plat de tous les tickers actifs."""
    tickers = []
    for actifs in watchlist.values():
        tickers.extend(actifs.keys())
    return tickers


def formater_prix(prix: float) -> str:
    """Formate un prix avec le bon nombre de décimales selon la valeur."""
    if prix is None:
        return "N/A"
    if prix >= 1000:
        return f"{prix:,.2f}"
    if prix >= 1:
        return f"{prix:.4f}"
    return f"{prix:.6f}"


def timestamp_maintenant() -> str:
    """Retourne le timestamp actuel au format ISO 8601."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def date_rapport() -> str:
    """Retourne la date du jour au format YYYY-MM-DD pour les noms de fichiers."""
    return datetime.utcnow().strftime("%Y-%m-%d")


def sauvegarder_rapport(contenu: str, dossier: str = "daily") -> str:
    """
    Sauvegarde un rapport dans reports/daily/ ou reports/weekly/.
    Retourne le chemin du fichier créé.
    """
    try:
        reports_dir = os.path.join(BASE_DIR, "reports", dossier)
        os.makedirs(reports_dir, exist_ok=True)

        nom_fichier = f"report_{date_rapport()}.md"
        chemin = os.path.join(reports_dir, nom_fichier)

        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)

        logger.info(f"Rapport sauvegardé : {chemin}")
        return chemin

    except Exception as e:
        logger.error(f"Erreur sauvegarde rapport : {e}")
        return ""
