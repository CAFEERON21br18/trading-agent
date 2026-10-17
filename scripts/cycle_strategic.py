"""
scripts/cycle_strategic.py — Cycle STRATÉGIQUE (toutes les 4h)
Monitor SL/TP, conseils sur le portefeuille réel, régime de marché.
Ne lance pas les explorateurs : le tactical le fait toutes les 15 min (TODO §19).
Ne traite pas la queue : seul le tactical l'analyse (TODO §18).
Skip si QUOTIDIEN tourne.
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import update_heartbeat
from utils.registre_cycles import ouvrir, clore

logger = get_logger("cycle_strategic")
CYCLE = "strategic"


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("🟢 Cycle STRATÉGIQUE — démarrage")
    skip, raison = doit_skipper(CYCLE)
    if skip:
        logger.info(f"Skip : {raison}")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    if not acquerir_lock(CYCLE):
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    passage = ouvrir("strategique")  # registre (Phase 4, R2), clos dans le finally
    try:
        from utils.portfolio_db import initialiser_paper_db
        from agents.paper_trader.monitor import monitorer_positions

        initialiser_paper_db()
        # 1. Monitor positions (les explorateurs et la queue sont au tactical, TODO §18-§19)
        monitorer_positions(passage)

        # v5.4.1 — Conseils sur le portefeuille réel (toutes les 4h)
        nb_conseils = 0
        try:
            from agents.real_advisor import evaluer_tout_le_portefeuille
            nb_conseils = evaluer_tout_le_portefeuille(passage)
            logger.info(f"Real advisor : {nb_conseils} conseil(s) générés")
        except Exception as e:
            logger.error(f"Real advisor échoué : {e}")

        # v5.5.0 — Détection régime de marché (global + actifs clés)
        regime_global_str = "indispo"
        try:
            from agents.technical_skills.market_regime import (
                detecter_regime_actif, detecter_regime_global, enregistrer_regime
            )
            from utils.real_portfolio_db import initialiser_real_db
            initialiser_real_db()  # s'assure que la table existe
            rg = detecter_regime_global()
            enregistrer_regime("global", rg)
            regime_global_str = f"{rg['regime_global']} ({rg['mode']})"
            logger.info(f"Régime global : {regime_global_str}")
            for tk in ("BTC-USD", "SPY", "NVDA", "AAPL", "QQQ"):
                r = detecter_regime_actif(tk)
                if r["regime"] != "indispo":
                    enregistrer_regime(tk, r)
                    logger.info(f"  Régime {tk:8s} : {r['regime']} (ADX {r['adx']})")
        except Exception as e:
            logger.error(f"Régime marché échoué : {e}")

        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"conseils_reels": nb_conseils,
                                "regime_global": regime_global_str})
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle STRATÉGIQUE échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        clore(passage)
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
