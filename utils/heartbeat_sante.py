"""
utils/heartbeat_sante.py — Lecture de la santé du système dans le heartbeat : retard des cycles,
panne de la routine quotidienne.
Sorti de utils/heartbeat.py (règle des 200 lignes) ; heartbeat.py le réexporte : importer ces
fonctions depuis utils.heartbeat, comme avant.
"""

from datetime import datetime, timezone


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


# En fin de module : import croisé avec utils.heartbeat, qui réexporte ce module. Placé ici, il
# fonctionne quel que soit le module importé en premier.
from utils.heartbeat import lire_heartbeat, SEUIL_ECHECS_CONSECUTIFS, SEUIL_PANNE_HEURES  # noqa: E402
