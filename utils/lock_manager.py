"""
utils/lock_manager.py — Système de lock entre les 5 cycles d'exécution
Évite que 2 cycles tournent en même temps et créent des races sur la BDD.

Hiérarchie d'exclusion :
- CRITIQUE  : ne vérifie jamais (toujours prioritaire)
- TACTIQUE  : skip si STRATÉGIQUE ou QUOTIDIEN tourne
- STRATÉGIQUE : skip si QUOTIDIEN tourne
- QUOTIDIEN/HEBDO : peuvent skip si l'autre tourne

Lock auto-expiré après 30 min (protection crash).
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

LOCK_DIR     = "/tmp"
LOCK_PREFIX  = "alphasignal_"
EXPIRATION_S = 30 * 60  # 30 minutes


def _chemin_lock(cycle: str) -> str:
    return os.path.join(LOCK_DIR, f"{LOCK_PREFIX}{cycle}.lock")


def acquerir_lock(cycle: str) -> bool:
    """
    Crée un lock file pour le cycle. Retourne True si acquis.
    Le lock est auto-libéré si > 30 min (protection crash).
    """
    chemin = _chemin_lock(cycle)
    if est_actif(cycle):
        logger.info(f"Lock {cycle} déjà actif — abandon")
        return False
    try:
        with open(chemin, "w") as f:
            json.dump({"cycle": cycle, "pid": os.getpid(),
                       "acquired_at": datetime.now(timezone.utc).isoformat()}, f)
        logger.info(f"Lock {cycle} acquis (pid {os.getpid()})")
        return True
    except Exception as e:
        logger.error(f"Impossible d'acquérir le lock {cycle} : {e}")
        return False


def liberer_lock(cycle: str) -> None:
    """Libère le lock du cycle (à la fin de l'exécution)."""
    chemin = _chemin_lock(cycle)
    try:
        if os.path.exists(chemin):
            os.remove(chemin)
            logger.info(f"Lock {cycle} libéré")
    except Exception as e:
        logger.error(f"Erreur libération lock {cycle} : {e}")


def est_actif(cycle: str) -> bool:
    """Retourne True si un lock existe et n'est pas expiré."""
    chemin = _chemin_lock(cycle)
    if not os.path.exists(chemin):
        return False
    try:
        age = time.time() - os.path.getmtime(chemin)
        if age > EXPIRATION_S:
            logger.warning(f"Lock {cycle} expiré (âge {age:.0f}s) — suppression")
            os.remove(chemin)
            return False
        return True
    except Exception as e:
        logger.error(f"Erreur vérification lock {cycle} : {e}")
        return False


def doit_skipper(cycle_courant: str) -> tuple[bool, str]:
    """
    Vérifie la hiérarchie d'exclusion. Retourne (skip, raison).
    """
    hierarchie = {
        "critical":  [],
        "tactical":  ["strategic", "daily", "weekly"],
        "strategic": ["daily", "weekly"],
        "daily":     ["weekly"],
        "weekly":    ["daily"],
    }
    bloqueurs = hierarchie.get(cycle_courant, [])
    for c in bloqueurs:
        if est_actif(c):
            return True, f"Cycle {c} en cours — {cycle_courant} skippé"
    return False, ""


def cycles_actifs() -> list[str]:
    """Liste des cycles actuellement actifs (non expirés)."""
    actifs = []
    for c in ("critical", "tactical", "strategic", "daily", "weekly"):
        if est_actif(c):
            actifs.append(c)
    return actifs
