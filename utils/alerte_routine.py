"""
utils/alerte_routine.py — Alerte « journée sans routine » (suite du registre v1.9, §9.8 a).

Quand la collecte des prix échoue au cycle quotidien après midi (heure de Lisbonne), c'est que la
collecte de 7h30 a échoué ou n'a pas tourné, et que le rattrapage de 12h échoue à son tour : il n'y
aura ni routine, ni rapport, ni observation Jev ce jour-là. Un seul e-mail par jour, avec la cause
journalisée. Avant midi, rien : le rattrapage de 12h retentera. Ne lève jamais.
"""

import json
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

from utils.logger import get_logger

logger = get_logger(__name__)

LISBONNE = ZoneInfo("Europe/Lisbon")
HEURE_RATTRAPAGE = time(12, 0)
SUJET = "⚠️ [AlphaSignal] Collecte des prix en échec, pas de routine ni d'observation Jev aujourd'hui"
ETAT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "cache", "alerte_sans_routine.json")


def _maintenant() -> datetime:
    return datetime.now(LISBONNE)


def _deja_envoyee(jour: str) -> bool:
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f).get("jour") == jour
    except (OSError, ValueError):
        return False


def alerter_journee_sans_routine(cause: str, maintenant: datetime | None = None, envoyer=None) -> bool:
    """Envoie l'alerte si on est après midi (Lisbonne) et qu'elle n'est pas déjà partie aujourd'hui.
    Rend True si un e-mail a été envoyé (ou confié au repli local de l'utilitaire)."""
    try:
        t = (maintenant or _maintenant()).astimezone(LISBONNE)
        jour = t.date().isoformat()
        if t.time() < HEURE_RATTRAPAGE or _deja_envoyee(jour):
            return False
        if envoyer is None:
            from alerts.channels.email_channel import envoyer_email as envoyer
        corps = (f"Collecte des prix en échec, pas de routine ni d'observation Jev aujourd'hui ({jour}).\n\n"
                 f"La collecte de 7h30 a échoué ou n'a pas tourné, et le rattrapage de 12h a échoué à "
                 f"{t:%H:%M} (heure de Lisbonne).\n\nCause journalisée : {cause}\n\n"
                 f"Détail : logs/daily.log et logs/task_daily.log. Le filet du tactical relancera une "
                 f"collecte si la dernière barre 1d a plus de 30 h. Paper trading uniquement.")
        envoyer(sujet=SUJET, corps_texte=corps)
        os.makedirs(os.path.dirname(ETAT), exist_ok=True)
        with open(ETAT, "w", encoding="utf-8") as f:
            json.dump({"jour": jour, "envoyee_a": t.isoformat(timespec="seconds"), "cause": cause[:300]}, f)
        logger.error(f"Journée sans routine ({jour}) : alerte envoyée. Cause : {cause}")
        return True
    except Exception as e:
        logger.error(f"Alerte « journée sans routine » impossible : {e}")
        return False
