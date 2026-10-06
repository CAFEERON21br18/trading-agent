"""
scripts/cycle_critical.py — Cycle CRITIQUE (toutes les 5 min, 24/7)
Vérifie les SL/TP des positions ouvertes (prioritaires : LOCK-IN d'abord).
Léger : < 30s, < 50 Mo RAM.
PAS de lock check (ce cycle est toujours prioritaire).
"""

import sys
import os
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock
from utils.heartbeat import update_heartbeat
from utils.registre_cycles import ouvrir, clore

logger = get_logger("cycle_critical")
CYCLE = "critical"


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("⚡ Cycle CRITIQUE — démarrage")
    if not acquerir_lock(CYCLE):
        logger.warning("Lock critical déjà acquis (instance précédente trop longue ?) — abandon")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    passage = ouvrir("critique")  # registre (Phase 4, R2) : clôtures SL/TP et stops déplacés
    try:
        from utils.portfolio_db import initialiser_paper_db
        from agents.paper_trader.monitor import monitorer_positions

        initialiser_paper_db()
        res = monitorer_positions(passage)
        logger.info(f"⚡ Critical : {res['verifiees']} surveillée(s), "
                    f"{res['fermees_tp']} TP, {res['fermees_sl']} SL, "
                    f"{res.get('lockin_actifs', 0)} LOCK-IN")
        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"positions_verifiees": res["verifiees"],
                                "fermees_tp": res["fermees_tp"], "fermees_sl": res["fermees_sl"]})
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle CRITIQUE échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        clore(passage, toujours=False)  # ligne de passage seulement s'il y a eu un événement
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
