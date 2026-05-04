"""
agents/paper_trader/lockin.py — Mode LOCK-IN (surveillance rapprochée)
Marque un actif pour vérification toutes les 5 min (cycle critique).
Utilisé pour les trades très court-terme (scalp, breakout en cours).
Auto-expiré après 4h.
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger(__name__)

CHEMIN_LOCKIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "lockin_assets.json",
)
DUREE_DEFAUT_H = 4   # auto-expiration après 4h
INTERVAL_DEFAUT_S = 300


def _lire() -> list[dict]:
    if not os.path.exists(CHEMIN_LOCKIN):
        return []
    try:
        with open(CHEMIN_LOCKIN, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lecture lockin échouée : {e}")
        return []


def _ecrire(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(CHEMIN_LOCKIN), exist_ok=True)
    with open(CHEMIN_LOCKIN, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def _expire_vieux(items: list[dict]) -> list[dict]:
    """Filtre les entrées non expirées."""
    now = datetime.now(timezone.utc)
    actifs = []
    for it in items:
        try:
            expire = datetime.fromisoformat(it["expires_at"])
            if now < expire:
                actifs.append(it)
            else:
                logger.info(f"LOCK-IN expiré pour {it['asset']}")
        except Exception:
            actifs.append(it)
    return actifs


def activer_lockin(ticker: str, raison: str, duree_h: float = DUREE_DEFAUT_H,
                   interval_s: int = INTERVAL_DEFAUT_S) -> dict:
    """Active le mode surveillance rapprochée sur un actif."""
    items = _expire_vieux(_lire())
    items = [it for it in items if it["asset"] != ticker]  # remplace l'éventuel existant

    now = datetime.now(timezone.utc)
    entree = {
        "asset":                  ticker,
        "reason":                 raison,
        "activated_at":           now.isoformat(timespec="seconds"),
        "expires_at":             (now + timedelta(hours=duree_h)).isoformat(timespec="seconds"),
        "check_interval_seconds": interval_s,
    }
    items.append(entree)
    _ecrire(items)
    logger.info(f"🔒 LOCK-IN activé sur {ticker} ({raison}) — expire dans {duree_h}h")
    return entree


def est_en_lockin(ticker: str) -> bool:
    return any(it["asset"] == ticker for it in _expire_vieux(_lire()))


def lister_lockin() -> list[dict]:
    """Retourne la liste des actifs en LOCK-IN actifs (et purge les expirés)."""
    actifs = _expire_vieux(_lire())
    _ecrire(actifs)  # persister la purge
    return actifs


def desactiver_lockin(ticker: str) -> bool:
    """Retire un actif de la liste (à la fermeture du trade ou manuellement)."""
    items = _lire()
    nouveaux = [it for it in items if it["asset"] != ticker]
    if len(nouveaux) == len(items):
        return False
    _ecrire(nouveaux)
    logger.info(f"🔓 LOCK-IN désactivé sur {ticker}")
    return True
