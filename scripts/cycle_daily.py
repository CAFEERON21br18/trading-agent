"""
scripts/cycle_daily.py — Cycle QUOTIDIEN (1×/jour à 7h30)
Routine complète : analyses + paper trading + rapport email.
Le plus prioritaire après le critique. Skip si HEBDO tourne.
"""

import sys
import os
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import (
    signaler_succes, signaler_echec, evaluer_sante, update_heartbeat, SEUIL_ECHECS_CONSECUTIFS,
)

logger = get_logger("cycle_daily")
CYCLE = "daily"

DOSSIER_RAPPORTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "daily",
)


def _rapport_du_jour_existe() -> bool:
    """Anti-doublon : si le rapport du jour est déjà généré, skip."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.exists(os.path.join(DOSSIER_RAPPORTS, f"report_{date_str}.md"))


def _alerter_panne_si_critique(tentatives: int) -> None:
    if tentatives < SEUIL_ECHECS_CONSECUTIFS:
        return
    try:
        from alerts.channels.email_channel import envoyer_email
        envoyer_email(
            sujet=f"⚠️ [AlphaSignal] PANNE — {tentatives} échecs consécutifs",
            corps_texte=f"AlphaSignal a échoué {tentatives} fois consécutivement.\n"
                        f"Lance : python scripts/check_status.py",
        )
    except Exception:
        pass


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("🔵 Cycle QUOTIDIEN — démarrage")
    if _rapport_du_jour_existe():
        logger.info("Rapport du jour déjà généré — skip")
        update_heartbeat(CYCLE, status="skipped_already_done", duration_sec=0)
        return 0
    skip, raison = doit_skipper(CYCLE)
    if skip:
        logger.info(f"Skip : {raison}")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    if not acquerir_lock(CYCLE):
        update_heartbeat(CYCLE, status="skipped_lock", duration_sec=0)
        return 0
    try:
        sante_avant = evaluer_sante()
        if not sante_avant["ok"]:
            logger.warning(f"État dégradé avant lancement : {sante_avant['raison']}")

        from utils.database import initialiser_base
        from scripts.fetch_data import collecter_toute_la_watchlist
        from utils.helpers import charger_watchlist
        from agents.orchestrator import lancer_routine_quotidienne

        initialiser_base()
        try:
            watchlist = charger_watchlist()
            if watchlist:
                collecter_toute_la_watchlist(watchlist)
        except Exception as e:
            logger.error(f"Collecte données : {e} (on continue)")

        resume = lancer_routine_quotidienne(envoyer_emails=True)
        signaler_succes(rapport_envoye=resume.get("rapport_envoye", False))
        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"signaux_forts": resume.get("signaux_forts", 0),
                                "rapport_envoye": resume.get("rapport_envoye", False)})
        logger.info(f"🔵 Quotidien terminé : {resume}")
        return 0
    except Exception as e:
        trace = traceback.format_exc()
        logger.error(f"❌ Cycle QUOTIDIEN échoué : {e}")
        logger.error(trace)
        nb = signaler_echec(f"{type(e).__name__}: {e}")
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        try:
            from alerts.channels.email_channel import envoyer_email
            envoyer_email(
                sujet=f"⚠️ [AlphaSignal] Erreur cycle quotidien (#{nb})",
                corps_texte=f"{e}\n\n{trace[:2000]}",
            )
        except Exception:
            pass
        _alerter_panne_si_critique(nb)
        return 1
    finally:
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
