"""
agents/explorers/queue_manager.py — File d'attente des découvertes des explorateurs
Stockée dans data/explorer_queue.json. Triée par score décroissant.
Une entrée par ticker et par jour de Lisbonne (data/cache/queue_du_jour.json) : un ticker analysé puis
retiré par le tactical ne revient que le lendemain (USDMXN=X occupait 18 % des analyses de la queue).
"""

import sys
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.passage import noter_passage

logger = get_logger(__name__)

CHEMIN_QUEUE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "explorer_queue.json",
)
MAX_QUEUE = 20
LISBONNE = ZoneInfo("Europe/Lisbon")


def _chemin_jour() -> str:
    """À côté de la queue (data/cache/queue_du_jour.json) : suit CHEMIN_QUEUE, y compris dans les tests."""
    return os.path.join(os.path.dirname(CHEMIN_QUEUE), "cache", "queue_du_jour.json")


def _jour() -> str:
    return datetime.now(LISBONNE).date().isoformat()


def _entres_aujourdhui() -> set[str]:
    """Tickers déjà entrés dans la queue aujourd'hui (jour de Lisbonne)."""
    try:
        with open(_chemin_jour(), encoding="utf-8") as f:
            d = json.load(f)
        return set(d.get("tickers", [])) if d.get("jour") == _jour() else set()
    except (OSError, ValueError):
        return set()


def _noter_entree(ticker: str) -> None:
    try:
        os.makedirs(os.path.dirname(_chemin_jour()), exist_ok=True)
        with open(_chemin_jour(), "w", encoding="utf-8") as f:
            json.dump({"jour": _jour(), "tickers": sorted(_entres_aujourdhui() | {ticker})}, f)
    except OSError as e:
        logger.error(f"Journal du jour de la queue : {e}")


def _lire() -> list[dict]:
    if not os.path.exists(CHEMIN_QUEUE):
        return []
    try:
        with open(CHEMIN_QUEUE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lecture queue : {e}")
        return []


def _ecrire(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(CHEMIN_QUEUE), exist_ok=True)
    with open(CHEMIN_QUEUE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def ajouter_decouverte(explorer: str, ticker: str, score: int,
                       filters_triggered: list[str], details: dict | None = None) -> bool:
    """
    Ajoute une découverte à la queue. Si l'actif y est déjà, garde le plus haut score.
    Retourne True si effectivement ajoutée/mise à jour.
    """
    items = _lire()

    # Si déjà dans la queue, on met à jour si le nouveau score est meilleur
    for it in items:
        if it["ticker"] == ticker:
            if score > it["score"]:
                it["score"] = score
                it["filters_triggered"] = filters_triggered
                it["details"] = details or {}
                it["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                _ecrire(items)
                return True
            return False

    # Nouvelle entrée : une seule par ticker et par jour, puis vérifier la capacité
    if ticker in _entres_aujourdhui():
        return False
    if len(items) >= MAX_QUEUE:
        # Si la queue est pleine, on remplace l'entrée la plus faible si le score est meilleur
        plus_faible = min(items, key=lambda x: x["score"])
        if score <= plus_faible["score"]:
            return False
        items.remove(plus_faible)

    items.append({
        "explorer":          explorer,
        "ticker":            ticker,
        "score":             score,
        "filters_triggered": filters_triggered,
        "details":           details or {},
        "discovery_date":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    items.sort(key=lambda x: x["score"], reverse=True)
    _ecrire(items)
    _noter_entree(ticker)
    return True


def lire_queue() -> list[dict]:
    items = _lire()
    noter_passage(logger, "Queue des découvertes", f"{len(items)} en attente")
    return items


def retirer(ticker: str) -> bool:
    """Retire un ticker de la queue (par ex. quand il est promu en watchlist)."""
    items = _lire()
    nouveaux = [it for it in items if it["ticker"] != ticker]
    if len(nouveaux) == len(items):
        return False
    _ecrire(nouveaux)
    return True


def vider() -> None:
    _ecrire([])
