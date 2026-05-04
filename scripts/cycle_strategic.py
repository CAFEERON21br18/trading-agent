"""
scripts/cycle_strategic.py — Cycle STRATÉGIQUE (toutes les 4h)
Lance les 7 explorateurs + traite la queue (analyses complètes).
Skip si QUOTIDIEN tourne.
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import update_heartbeat

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
    try:
        from utils.portfolio_db import initialiser_paper_db
        from agents.paper_trader.monitor import monitorer_positions
        from agents.explorers.crypto_explorer.explorer    import CryptoExplorer
        from agents.explorers.stock_explorer.explorer     import StockExplorer
        from agents.explorers.index_explorer.explorer     import IndexExplorer
        from agents.explorers.etf_explorer.explorer       import ETFExplorer
        from agents.explorers.commodity_explorer.explorer import CommodityExplorer
        from agents.explorers.forex_explorer.explorer     import ForexExplorer
        from agents.explorers.cfd_index_explorer.explorer import CFDIndexExplorer
        from agents.explorers.queue_manager import lire_queue

        initialiser_paper_db()
        # 1. Monitor positions
        monitorer_positions()

        # 2. Lancer les 7 explorateurs
        explorateurs = [
            ("crypto",    CryptoExplorer(nb_max=50)),
            ("stock",     StockExplorer()),
            ("index",     IndexExplorer()),
            ("etf",       ETFExplorer()),
            ("commodity", CommodityExplorer()),
            ("forex",     ForexExplorer()),
            ("cfd_index", CFDIndexExplorer()),
        ]
        total_decouvertes = 0
        for nom, exp in explorateurs:
            try:
                res = exp.scanner()
                total_decouvertes += len(res["decouvertes"])
            except Exception as e:
                logger.error(f"Explorer {nom} échoué : {e}")

        queue = lire_queue()
        logger.info(f"Stratégique : {total_decouvertes} découverte(s), queue à {len(queue)} actifs")
        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"decouvertes": total_decouvertes, "queue_len": len(queue)})
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle STRATÉGIQUE échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
