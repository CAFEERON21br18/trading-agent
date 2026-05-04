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


# Délais maximum acceptables avant qu'un cycle soit considéré "en retard" (en minutes)
DELAIS_MAX_MIN = {
    "critical":  10,    # 5 min × 2
    "tactical":  45,    # 30 min + marge
    "strategic": 300,   # 4h + 1h
    "daily":     1500,  # 25h
    "weekly":    10500, # 7.3 jours
    "cleanup":   10500,
}


def evaluer_sante_cycles() -> dict:
    """
    Retourne par cycle :
      { name: {last_run, time_ago, runs_today, is_late, is_dead, status, duration_sec} }
    """
    hb = lire_heartbeat()
    cycles = hb.get("cycles", {})
    now = datetime.now(timezone.utc)
    res = {}
    for name in ("critical", "tactical", "strategic", "daily", "weekly", "cleanup"):
        info = cycles.get(name, {})
        if not info or not info.get("last_run"):
            res[name] = {"jamais": True, "status": "unknown"}
            continue
        try:
            last = datetime.fromisoformat(info["last_run"])
            delta_min = (now - last).total_seconds() / 60
        except Exception:
            res[name] = {"jamais": True, "status": "unknown"}
            continue

        seuil = DELAIS_MAX_MIN.get(name, 60)
        # Format human "il y a X min" / "il y a Xh" / "il y a X jours"
        if delta_min < 60:
            time_ago = f"il y a {int(delta_min)} min"
        elif delta_min < 1440:
            time_ago = f"il y a {int(delta_min // 60)}h{int(delta_min % 60):02d}"
        else:
            time_ago = f"il y a {int(delta_min // 1440)}j"

        res[name] = {
            "jamais":        False,
            "last_run":      info["last_run"],
            "time_ago":      time_ago,
            "runs_today":    info.get("runs_today", 0),
            "duration_sec":  info.get("duration_sec", 0),
            "status":        info.get("status", "healthy"),
            "is_late":       delta_min > seuil,
            "is_dead":       delta_min > seuil * 3,
            "minutes_ago":   round(delta_min, 1),
        }
    return res


def evaluer_sante() -> dict:
    """
    Évalue la santé du système. Retourne :
      { "ok": bool, "raison": str, "heures_depuis_dernier_run": float|None,
        "consecutive_failures": int, "status": str }
    """
    hb = lire_heartbeat()
    if not hb or not hb.get("last_successful_run"):
        return {"ok": False, "raison": "Aucun run réussi enregistré",
                "heures_depuis_dernier_run": None,
                "consecutive_failures": hb.get("consecutive_failures", 0),
                "status": "unknown"}

    try:
        dernier = datetime.fromisoformat(hb["last_successful_run"])
        delta   = datetime.now(timezone.utc) - dernier
        heures  = delta.total_seconds() / 3600
    except Exception as e:
        return {"ok": False, "raison": f"Date invalide : {e}",
                "heures_depuis_dernier_run": None,
                "consecutive_failures": hb.get("consecutive_failures", 0),
                "status": "unknown"}

    nb_echecs = hb.get("consecutive_failures", 0)
    if heures > SEUIL_PANNE_HEURES:
        return {"ok": False, "raison": f"Aucun run réussi depuis {heures:.1f}h (seuil {SEUIL_PANNE_HEURES}h)",
                "heures_depuis_dernier_run": heures, "consecutive_failures": nb_echecs,
                "status": "critical"}
    if nb_echecs >= SEUIL_ECHECS_CONSECUTIFS:
        return {"ok": False, "raison": f"{nb_echecs} échecs consécutifs",
                "heures_depuis_dernier_run": heures, "consecutive_failures": nb_echecs,
                "status": "critical"}
    return {"ok": True, "raison": "OK", "heures_depuis_dernier_run": heures,
            "consecutive_failures": nb_echecs, "status": hb.get("status", "healthy")}
