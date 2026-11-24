"""
utils/heartbeat.py — Système de heartbeat pour détecter les pannes du scheduler
Fichier : data/heartbeat.json — mis à jour à chaque exécution réussie de la routine.
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

CHEMIN_HEARTBEAT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "heartbeat.json",
)
SEUIL_PANNE_HEURES        = 26   # > 26h depuis dernier run = panne
SEUIL_ECHECS_CONSECUTIFS  = 3    # 3 échecs = alerte critique


def _maintenant_iso() -> str:
    """Timestamp UTC ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lire_heartbeat() -> dict:
    """Lit le heartbeat actuel ; retourne un dict vide si absent."""
    if not os.path.exists(CHEMIN_HEARTBEAT):
        return {}
    try:
        with open(CHEMIN_HEARTBEAT, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lecture heartbeat échouée : {e}")
        return {}


def _ecrire(data: dict) -> None:
    os.makedirs(os.path.dirname(CHEMIN_HEARTBEAT), exist_ok=True)
    with open(CHEMIN_HEARTBEAT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def signaler_succes(rapport_envoye: bool = True) -> None:
    """À appeler à la fin d'une routine quotidienne réussie."""
    hb = lire_heartbeat()
    hb["last_successful_run"] = _maintenant_iso()
    if rapport_envoye:
        hb["last_report_sent"] = _maintenant_iso()
    hb["consecutive_failures"] = 0
    hb["status"] = "healthy"
    _ecrire(hb)
    logger.info("Heartbeat mis à jour : healthy")


def signaler_echec(message: str) -> int:
    """À appeler après une exception. Retourne le nb d'échecs consécutifs."""
    hb = lire_heartbeat()
    hb["consecutive_failures"] = hb.get("consecutive_failures", 0) + 1
    hb["last_failure"]         = _maintenant_iso()
    hb["last_error"]           = message[:500]
    hb["status"] = "critical" if hb["consecutive_failures"] >= SEUIL_ECHECS_CONSECUTIFS else "degraded"
    _ecrire(hb)
    logger.warning(f"Heartbeat : {hb['consecutive_failures']} échec(s) consécutif(s) — statut {hb['status']}")
    return hb["consecutive_failures"]


# ── Heartbeat par cycle (v4.1) ───────────────────────────────────────────────

def update_heartbeat(cycle_name: str, status: str = "healthy",
                     duration_sec: float = 0, extra: dict | None = None) -> None:
    """
    Mise à jour du heartbeat pour UN cycle précis (critical/tactical/strategic/...).
    Ne fait jamais crasher l'appelant — silently ignore les erreurs.
    """
    try:
        hb = lire_heartbeat()
        if "cycles" not in hb:
            hb["cycles"] = {}

        # Compter les runs du jour (reset à minuit UTC)
        ancien = hb["cycles"].get(cycle_name, {})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        runs_today = ancien.get("runs_today", 0)
        if ancien.get("date") != today:
            runs_today = 0
        runs_today += 1

        hb["cycles"][cycle_name] = {
            "last_run":     _maintenant_iso(),
            "status":       status,
            "duration_sec": round(duration_sec, 1),
            "runs_today":   runs_today,
            "date":         today,
        }
        if extra:
            hb["cycles"][cycle_name].update(extra)
        hb["last_updated"] = _maintenant_iso()
        _ecrire(hb)
    except Exception as e:
        logger.error(f"update_heartbeat({cycle_name}) : {e}")


def update_heartbeat_explorer(explorer_name: str, stats: dict) -> None:
    """Heartbeat par explorateur — stocké séparément pour le dashboard."""
    try:
        hb = lire_heartbeat()
        if "explorers" not in hb:
            hb["explorers"] = {}
        hb["explorers"][explorer_name] = {
            "last_scan": _maintenant_iso(),
            **stats,
        }
        hb["last_updated"] = _maintenant_iso()
        _ecrire(hb)
    except Exception as e:
        logger.error(f"update_heartbeat_explorer({explorer_name}) : {e}")


# Santé du système : dans utils/heartbeat_sante.py (règle des 200 lignes). Import en fin de module,
# après les définitions que heartbeat_sante lit ici.
from utils.heartbeat_sante import DELAIS_MAX_MIN, evaluer_sante_cycles, evaluer_sante  # noqa: E402,F401 — réexport
