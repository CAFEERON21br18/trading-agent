"""
dashboard/api/etat_taches.py — État des tâches planifiées \\AlphaSignal\\ (vue temps réel, Phase 3).

LECTURE SEULE : un seul appel PowerShell (Get-ScheduledTask + Get-ScheduledTaskInfo), délai court
(DELAI_S), gardé en mémoire CACHE_S secondes pour toutes les pages ouvertes. Si l'appel échoue
(délai dépassé, PowerShell absent, sortie illisible), lire_taches() rend None : l'état des tâches
s'affiche « inconnu ». Rien n'est lancé ni modifié (aucun schtasks /Run, /End ni /Change).
"""

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

from utils.logger import get_logger

logger = get_logger(__name__)

DOSSIER = "\\AlphaSignal\\"
DELAI_S = 6
CACHE_S = 25
# Codes de LastTaskResult qui ne sont pas des erreurs : succès, prête, en cours, jamais lancée
CODES_SANS_ERREUR = {0, 0x41300, 0x41301, 0x41303}
_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    f"Get-ScheduledTask -TaskPath '{DOSSIER}' | ForEach-Object {{ $i = $_ | Get-ScheduledTaskInfo; "
    "[pscustomobject]@{ nom = $_.TaskName; etat = [string]$_.State; "
    "dernier = $(if ($i.LastRunTime) { $i.LastRunTime.ToString('o') }); code = $i.LastTaskResult; "
    "prochain = $(if ($i.NextRunTime) { $i.NextRunTime.ToString('o') }); "
    "declencheurs = @($_.Triggers | ForEach-Object { [pscustomobject]@{ "
    "classe = $_.CimClass.CimClassName; intervalle = $_.Repetition.Interval; "
    "jours = $_.DaysInterval; semaines = $_.WeeksInterval } }) } } | ConvertTo-Json -Depth 4 -Compress"
)

_cache = {"quand": 0.0, "valeur": None}
_verrou = threading.Lock()


def _date(valeur):
    """Date ISO de PowerShell, ou None (absente, vide, ou valeur de 1959 des déclencheurs hebdo)."""
    if not isinstance(valeur, str) or not valeur:
        return None
    try:
        d = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.year >= 2000 else None


def _duree_iso(texte):
    """'PT15M', 'PT4H', 'P1D' -> timedelta (None si illisible)."""
    if not isinstance(texte, str) or not texte.startswith("P"):
        return None
    total, nombre, partie_heure = 0, "", False
    unites = {"D": 86400, "H": 3600, "M": 60, "S": 1}
    for car in texte[1:]:
        if car == "T":
            partie_heure = True
        elif car.isdigit():
            nombre += car
        elif car in unites and nombre:
            total += int(nombre) * (unites[car] if partie_heure or car == "D" else 0)
            nombre = ""
    return timedelta(seconds=total) if total else None


def periode(tache: dict):
    """Période attendue entre deux lancements, d'après les déclencheurs (None : au démarrage, etc.)."""
    periodes = []
    for d in tache.get("declencheurs") or []:
        intervalle = _duree_iso(d.get("intervalle"))
        if intervalle:
            periodes.append(intervalle)
        elif d.get("classe") == "MSFT_TaskDailyTrigger":
            periodes.append(timedelta(days=d.get("jours") or 1))
        elif d.get("classe") == "MSFT_TaskWeeklyTrigger":
            periodes.append(timedelta(weeks=d.get("semaines") or 1))
    return min(periodes) if periodes else None


def _normaliser(brut) -> dict:
    taches = brut if isinstance(brut, list) else [brut]
    sortie = {}
    for t in taches:
        if not isinstance(t, dict) or not t.get("nom"):
            continue
        code = t.get("code")
        sortie[t["nom"]] = {
            "nom": t["nom"], "etat": t.get("etat"), "dernier": _date(t.get("dernier")),
            "prochain": _date(t.get("prochain")), "code": code,
            "en_erreur": isinstance(code, int) and code not in CODES_SANS_ERREUR and t.get("etat") != "Running",
            "periode": periode(t)}
    return sortie


def _interroger():
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=DELAI_S, **options)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"code {r.returncode} : {r.stderr.strip()[:200]}")
    return _normaliser(json.loads(r.stdout))


def lire_taches():
    """{nom: tâche} des tâches \\AlphaSignal\\, ou None si la lecture échoue (état « inconnu »)."""
    with _verrou:
        if time.monotonic() - _cache["quand"] < CACHE_S:
            return _cache["valeur"]
        try:
            valeur = _interroger()
        except Exception as e:  # délai dépassé, PowerShell absent, JSON illisible…
            logger.warning(f"Tâches planifiées illisibles : {type(e).__name__} {e}")
            valeur = None
        _cache.update(quand=time.monotonic(), valeur=valeur)
        return valeur
