"""
scripts/surveiller_dashboard.py — Surveillance du dashboard (TODO §34), toutes les 5 minutes.

Lancement : .venv\\Scripts\\python.exe scripts\\surveiller_dashboard.py
(tâche \\AlphaSignal\\surveillance créée par scripts\\installer_surveillance.ps1, à lancer à la main)

À chaque passage : GET http://127.0.0.1:<DASHBOARD_PORT>/api/health, délai de 5 s, sans proxy.
- 2 échecs consécutifs = incident : UN email (alerts/channels/email_channel.envoyer_email), puis un
  email de retour à la normale quand le dashboard répond de nouveau ;
- si rien n'écoute sur le port : relance de la tâche \\AlphaSignal\\dashboard (schtasks /Run), au plus
  une fois par RELANCE_MIN_S, et JAMAIS si la tâche est déjà en cours (Running) ou démarrée il y a
  moins de DEMARRAGE_RECENT_S (relance manuelle en cours), ni si son état est illisible ;
  si le port écoute sans répondre : alerte seulement (rien n'est tué).
L'état (échecs consécutifs, incident en cours, email envoyé, dernière relance) est gardé dans
data/surveillance_dashboard.json. Le script ne lève jamais : code de sortie 0.
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from utils.logger import get_logger  # noqa: E402

logger = get_logger("surveiller_dashboard")

HOTE = "127.0.0.1"
PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
URL = f"http://{HOTE}:{PORT}/api/health"
DELAI_S = 5
ECHECS_INCIDENT = 2
RELANCE_MIN_S = 15 * 60
DEMARRAGE_RECENT_S = 3 * 60
TACHE = r"\AlphaSignal\dashboard"
ETAT = os.path.join(RACINE, "data", "surveillance_dashboard.json")


def sonder(url: str = URL) -> tuple[bool, str]:
    """(répond, détail) : HTTP 200 avec un JSON lisible, en DELAI_S secondes au plus."""
    try:
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais de proxy
        with ouvreur.open(url, timeout=DELAI_S) as r:
            json.loads(r.read().decode("utf-8"))
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"{type(e).__name__} : {str(e)[:120]}"


def port_ecoute(hote: str = HOTE, port: int = PORT) -> bool:
    try:
        with socket.create_connection((hote, port), timeout=2):
            return True
    except OSError:
        return False


def raison_de_ne_pas_relancer(maintenant: datetime) -> str | None:
    """Pourquoi ne pas relancer la tâche, d'après son état (Get-ScheduledTaskInfo, délai court)."""
    try:
        from dashboard.api.etat_taches import lire_taches
        tache = (lire_taches() or {}).get(TACHE.rsplit("\\", 1)[-1])
    except Exception as e:
        tache = None
        logger.warning(f"État de {TACHE} illisible : {e}")
    if tache is None:
        return "état de la tâche illisible"
    if tache["etat"] == "Running":
        return "la tâche est déjà en cours (Running)"
    if tache["dernier"] and (maintenant - tache["dernier"]).total_seconds() < DEMARRAGE_RECENT_S:
        return f"tâche démarrée le {tache['dernier']:%d/%m %H:%M:%S}, il y a moins de 3 minutes"
    return None


def relancer() -> tuple[bool, str]:
    try:
        r = subprocess.run(["schtasks", "/Run", "/TN", TACHE], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout or r.stderr or "").strip()[:200]
    except Exception as e:
        return False, f"{type(e).__name__} : {e}"


def envoyer(sujet: str, corps: str) -> bool:
    from alerts.channels.email_channel import envoyer_email
    return bool(envoyer_email(sujet=sujet, corps_texte=corps))


def lire_etat() -> dict:
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ecrire_etat(etat: dict) -> None:
    os.makedirs(os.path.dirname(ETAT), exist_ok=True)
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1)


def passage(etat: dict, maintenant: datetime) -> dict:
    """Nouvel état après un contrôle (fonctions sonder, port_ecoute, relancer et envoyer du module)."""
    iso = maintenant.isoformat(timespec="seconds")
    ok, detail = sonder()
    if ok:
        if etat.get("incident") and etat.get("email_incident"):
            envoyer("✅ [AlphaSignal] Dashboard de nouveau joignable",
                    f"Le dashboard répond de nouveau ({URL}) depuis {iso}.\nIncident commencé le {etat.get('depuis')}.")
        if etat.get("incident"):
            logger.info(f"Dashboard de nouveau joignable (incident depuis {etat.get('depuis')})")
        return {"echecs": 0, "incident": False, "dernier_ok": iso}
    nouvel = {**etat, "echecs": int(etat.get("echecs", 0)) + 1, "dernier_echec": iso, "detail": detail}
    logger.warning(f"Dashboard sans réponse ({detail}) — échec n°{nouvel['echecs']}")
    if nouvel["echecs"] < ECHECS_INCIDENT:
        return nouvel
    if not nouvel.get("incident"):
        nouvel.update(incident=True, depuis=iso, email_incident=False)
    ecoute = port_ecoute()
    action = "le port écoute sans répondre : alerte seulement, rien n'est relancé"
    if not ecoute:
        derniere = nouvel.get("derniere_relance")
        delai_ecoule = not derniere or (maintenant - datetime.fromisoformat(derniere)).total_seconds() >= RELANCE_MIN_S
        refus = raison_de_ne_pas_relancer(maintenant) if delai_ecoule else None
        if refus:
            nouvel["relance"] = f"pas de relance : {refus}"
            logger.warning(f"Rien n'écoute sur {PORT}, pas de relance de {TACHE} : {refus}")
        elif delai_ecoule:
            r_ok, r_detail = relancer()
            nouvel.update(derniere_relance=iso, relance=r_detail)
            logger.warning(f"Rien n'écoute sur {PORT} : relance de {TACHE} ({'OK' if r_ok else 'échec'} : {r_detail})")
        action = f"rien n'écoute sur le port {PORT} : relance de la tâche {TACHE} ({nouvel.get('relance', '')})"
    if not nouvel.get("email_incident"):
        nouvel["email_incident"] = envoyer(
            "🚨 [AlphaSignal] Dashboard injoignable",
            f"{URL} ne répond plus depuis {nouvel['depuis']} ({nouvel['echecs']} contrôles en échec, "
            f"délai {DELAI_S} s).\nDernière erreur : {detail}\nAction : {action}.")
    return nouvel


def main() -> int:
    try:
        ecrire_etat(passage(lire_etat(), datetime.now(timezone.utc)))
    except Exception as e:
        logger.error(f"Surveillance du dashboard : {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
