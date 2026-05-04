"""
scripts/cycle_tactical.py — Cycle TACTIQUE (toutes les 30 min, 24/7)
Point de situation rapide :
- Monitor des positions
- Lit la queue d'exploration → si découvertes ≥ 8, lance le Decision Engine
- Skip si STRATEGIQUE / QUOTIDIEN tourne déjà
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import update_heartbeat

logger = get_logger("cycle_tactical")
CYCLE = "tactical"
SEUIL_FORT = 8  # score d'opportunité min pour analyse complète


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("🟡 Cycle TACTIQUE — démarrage")
    skip, raison = doit_skipper(CYCLE)
    if skip:
        logger.info(f"Skip : {raison}")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    if not acquerir_lock(CYCLE):
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    try:
        from utils.portfolio_db import initialiser_paper_db
        from agents.paper_trader.monitor import monitorer_positions
        from agents.explorers.queue_manager import lire_queue, retirer
        from agents.asset_analyzer import analyser_actif_complet
        from agents.decision_engine import decider
        from agents.paper_trader.cycle import executer_ouvertures

        initialiser_paper_db()
        # 1. Monitor positions
        monitorer_positions()

        # 2. Lire la queue → traiter les opportunités fortes (score ≥ 8)
        queue = lire_queue()
        opportunites = [q for q in queue if q["score"] >= SEUIL_FORT]
        logger.info(f"Queue : {len(queue)} découverte(s), {len(opportunites)} fortes (≥{SEUIL_FORT}/10)")

        decisions = []
        for q in opportunites[:5]:  # max 5 analyses par cycle tactique pour rester rapide
            ticker = q["ticker"]
            try:
                analyses = analyser_actif_complet(ticker)
                decision = decider(ticker, analyses)
                decisions.append({"ticker": ticker, "decision": decision, "analyses": analyses})
                if decision["decision"] in ("BUY", "SELL"):
                    retirer(ticker)  # promu vers exécution
            except Exception as e:
                logger.error(f"Analyse opportunité {ticker} échouée : {e}")

        # 3. Exécuter les BUY/SELL via le pipeline complet (BM → RM → Paper)
        ouvertures = 0
        if decisions:
            res = executer_ouvertures(decisions)
            ouvertures = len(res["ouvertes"])
            logger.info(f"Tactique : {ouvertures} position(s) ouverte(s) sur opportunités")
        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"queue_len": len(queue), "opportunites": len(opportunites),
                                "ouvertures": ouvertures})
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle TACTIQUE échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
