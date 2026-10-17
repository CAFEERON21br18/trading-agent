"""
agents/plans_quotidien.py — Contrôle quotidien des plans réels (TODO §30), à la fin du cycle de 7h30.

verifier_tous_les_plans n'était lancé que par le bouton de la page Plans. Le cycle quotidien l'appelle
désormais une fois par jour, après toute la routine (décisions, ouvertures, Jev, rapport, emails) :
seulement avant midi, heure de Lisbonne, donc au passage de 7h30 (même rattrapé plus tard dans la
matinée) et jamais à celui de 12h. Les alertes vont dans plan_alerts et sur la page Plans ; aucun
email. plan_advisor ne réinsère pas une alerte du même plan et du même type tant qu'elle est active.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from utils.logger import get_logger

logger = get_logger(__name__)

LISBONNE = ZoneInfo("Europe/Lisbon")
HEURE_LIMITE = 12  # passage de 12h : pas de contrôle des plans


def controler_les_plans(maintenant: datetime | None = None) -> int | None:
    """Nombre d'alertes créées, ou None pour un passage de midi ou plus tard."""
    heure = (maintenant or datetime.now(LISBONNE)).astimezone(LISBONNE).hour
    if heure >= HEURE_LIMITE:
        logger.info("Contrôle des plans : réservé au passage de 7h30, rien à ce passage")
        return None
    from agents.plan_advisor import verifier_tous_les_plans
    n = verifier_tous_les_plans()
    logger.info(f"Contrôle des plans : {n} alerte(s) créée(s)")
    return n
