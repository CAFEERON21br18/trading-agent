"""
scripts/daily_routine.py — Point d'entrée pour launchd
Routine incassable : try/except global, anti-doublon, heartbeat, alerte panne.
Appelé automatiquement à 7h30 et 12h00, et au chargement (RunAtLoad).
"""

import sys
import os
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.heartbeat import (
    signaler_succes, signaler_echec, evaluer_sante, SEUIL_ECHECS_CONSECUTIFS,
)

logger = get_logger(__name__)

DOSSIER_RAPPORTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "daily",
)


def _rapport_du_jour_existe() -> bool:
    """Anti-doublon : si le rapport du jour est déjà généré, skip."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    chemin = os.path.join(DOSSIER_RAPPORTS, f"report_{date_str}.md")
    return os.path.exists(chemin)


def _alerter_panne_si_critique(tentatives: int) -> None:
    """Envoie une alerte si on dépasse le seuil critique (3 échecs consécutifs)."""
    if tentatives < SEUIL_ECHECS_CONSECUTIFS:
        return
    try:
        from alerts.channels.email_channel import envoyer_email
        envoyer_email(
            sujet=f"⚠️ [AlphaSignal] PANNE — {tentatives} échecs consécutifs",
            corps_texte=(f"AlphaSignal a échoué {tentatives} fois consécutivement.\n\n"
                         f"Vérifie les logs dans ~/trading-agent/logs/errors.log\n"
                         f"Lance le diagnostic : python scripts/check_health.py"),
        )
    except Exception as e:
        logger.error(f"Impossible d'envoyer l'alerte de panne : {e}")


def _executer_routine_complete() -> dict:
    """Cœur de la routine : collecte → analyse → email. Peut lever des exceptions."""
    from utils.database import initialiser_base
    from scripts.fetch_data import collecter_toute_la_watchlist
    from utils.helpers import charger_watchlist
    from agents.orchestrator import lancer_routine_quotidienne

    initialiser_base()
    watchlist = charger_watchlist()
    if watchlist:
        logger.info("Collecte de données fraîches...")
        try:
            collecter_toute_la_watchlist(watchlist)
        except Exception as e:
            logger.error(f"Erreur collecte données (on continue) : {e}")

    return lancer_routine_quotidienne(envoyer_emails=True)


def main():
    logger.info("=" * 60)
    logger.info("AlphaSignal — Routine quotidienne (déclenchée par launchd)")
    logger.info("=" * 60)

    # ── Anti-doublon : si le rapport du jour est déjà généré, on s'arrête ─────
    if _rapport_du_jour_existe():
        logger.info("Rapport du jour déjà généré — skip (déclenchement RunAtLoad ou doublon).")
        return 0

    # ── Pré-check santé ──────────────────────────────────────────────────────
    sante_avant = evaluer_sante()
    if not sante_avant["ok"]:
        logger.warning(f"État dégradé avant lancement : {sante_avant['raison']}")

    # ── Exécution wrappée ────────────────────────────────────────────────────
    try:
        resume = _executer_routine_complete()
        signaler_succes(rapport_envoye=resume.get("rapport_envoye", False))
        logger.info(f"Routine terminée avec succès : {resume}")
        return 0

    except Exception as e:
        trace = traceback.format_exc()
        logger.error(f"❌ ROUTINE QUOTIDIENNE ÉCHOUÉE : {e}")
        logger.error(trace)

        nb_echecs = signaler_echec(f"{type(e).__name__}: {e}")

        # Tenter d'alerter par email (best-effort, ne pas planter ici)
        try:
            from alerts.channels.email_channel import envoyer_email
            envoyer_email(
                sujet=f"⚠️ [AlphaSignal] Erreur routine quotidienne (échec #{nb_echecs})",
                corps_texte=f"La routine a échoué :\n\n{e}\n\n--- Stack trace ---\n{trace[:2000]}",
            )
        except Exception as e2:
            logger.error(f"Impossible d'envoyer email d'alerte : {e2}")

        _alerter_panne_si_critique(nb_echecs)
        return 1


if __name__ == "__main__":
    sys.exit(main())
