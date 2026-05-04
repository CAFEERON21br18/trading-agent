"""
scripts/cycle_tactical.py — Cycle TACTIQUE (toutes les 15 min, 24/7) — v4.1
CŒUR de l'agent. Fait TOUT à chaque run :
  1. Monitor positions ouvertes (peut FERMER si SL/TP touché)
  2. Lance les 7 explorateurs (peut DÉCOUVRIR à tout moment)
  3. Analyse les opportunités fraîches → trade si BUY/SELL
  4. Analyse la watchlist active → trade si BUY/SELL
  5. Réévalue les positions ouvertes (peut FERMER ou ajuster)
Skip si STRATEGIQUE / QUOTIDIEN tourne déjà.
"""

import sys
import os
import time
import traceback
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import update_heartbeat

logger = get_logger("cycle_tactical")
CYCLE = "tactical"


def _lancer_explorateurs() -> tuple[int, int]:
    """Lance les 7 explorateurs. Retourne (total_decouvertes, total_observations)."""
    explorer_configs = [
        ("Crypto",    "agents.explorers.crypto_explorer.explorer",    "CryptoExplorer"),
        ("Stock",     "agents.explorers.stock_explorer.explorer",     "StockExplorer"),
        ("Index",     "agents.explorers.index_explorer.explorer",     "IndexExplorer"),
        ("ETF",       "agents.explorers.etf_explorer.explorer",       "ETFExplorer"),
        ("Commodity", "agents.explorers.commodity_explorer.explorer", "CommodityExplorer"),
        ("Forex",     "agents.explorers.forex_explorer.explorer",     "ForexExplorer"),
        ("CFD Index", "agents.explorers.cfd_index_explorer.explorer", "CFDIndexExplorer"),
    ]
    total_dec, total_obs = 0, 0
    for name, module_path, class_name in explorer_configs:
        try:
            module = __import__(module_path, fromlist=[class_name])
            ExplorerClass = getattr(module, class_name)
            res = ExplorerClass().scanner()
            total_dec += len(res["decouvertes"])
            total_obs += len(res.get("observations", []))
            gc.collect()
        except Exception as e:
            logger.error(f"  ❌ {name} Explorer : {e}")
    logger.info(f"  📊 Total : {total_dec} découvertes + {total_obs} observations")
    return total_dec, total_obs


def _analyser_et_trader(tickers: list[str], source: str) -> tuple[int, int]:
    """Pour chaque ticker, lance Decision Engine + tente d'ouvrir.
    Retourne (analyses, ouvertures)."""
    if not tickers:
        return 0, 0
    from agents.asset_analyzer import analyser_actif_complet
    from agents.decision_engine import decider
    from agents.paper_trader.cycle import executer_ouvertures

    decisions = []
    for t in tickers:
        try:
            analyses = analyser_actif_complet(t)
            decision = decider(t, analyses)
            decisions.append({"ticker": t, "decision": decision, "analyses": analyses})
        except Exception as e:
            logger.error(f"  ⚠️ Analyse {t} ({source}) : {str(e)[:80]}")
    ouvertures = 0
    if decisions:
        try:
            res = executer_ouvertures(decisions)
            ouvertures = len(res.get("ouvertes", []))
        except Exception as e:
            logger.error(f"  ⚠️ Exécution ouvertures ({source}) : {e}")
    logger.info(f"  📈 [{source}] {len(decisions)} analysés → {ouvertures} ouverture(s)")
    return len(decisions), ouvertures


def _reevaluer_positions() -> int:
    """Réévalue chaque position ouverte. Ferme si signal inverse fort."""
    from utils.portfolio_db import lire_positions_ouvertes, fermer_position as db_fermer
    from agents.asset_analyzer import analyser_actif_complet
    from agents.decision_engine import reevaluer_position
    from agents.paper_trader.executor import fermer_position

    positions = lire_positions_ouvertes()
    if not positions:
        return 0
    fermes = 0
    for p in positions:
        try:
            analyses = analyser_actif_complet(p["ticker"])
            verdict = reevaluer_position(p, analyses)
            if verdict["action"] == "CLOSE":
                from agents.paper_trader.portfolio import prix_actuel
                prix = prix_actuel(p["ticker"])
                if prix:
                    fermer_position(p["id"], prix, verdict["raison"], "CLOSED_REVERSAL")
                    fermes += 1
                    logger.info(f"  🔒 Position fermée par réévaluation : {p['ticker']} — {verdict['raison']}")
        except Exception as e:
            logger.error(f"  ⚠️ Réévaluation {p.get('ticker', '?')} : {e}")
    return fermes


def main() -> int:
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("🟡 CYCLE TACTIQUE v4.1 — démarrage")

    skip, raison = doit_skipper(CYCLE)
    if skip:
        logger.info(f"Skip : {raison}")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    if not acquerir_lock(CYCLE):
        update_heartbeat(CYCLE, status="skipped_lock", duration_sec=0)
        return 0

    try:
        from utils.portfolio_db import initialiser_paper_db
        from utils.helpers import charger_watchlist, tous_les_tickers
        from agents.paper_trader.monitor import monitorer_positions

        initialiser_paper_db()

        # 1. Monitor positions (SL/TP)
        logger.info("📍 ÉTAPE 1 — Monitor positions (SL/TP)")
        monitorer_positions()

        # 2. Lancer les 7 explorateurs
        logger.info("🔍 ÉTAPE 2 — Scan des 7 explorateurs")
        total_dec, total_obs = _lancer_explorateurs()

        # 3. Trade sur les opportunités fraîches (queue)
        logger.info("📊 ÉTAPE 3 — Opportunités du queue")
        from agents.explorers.queue_manager import lire_queue, retirer
        opportunites = [q for q in lire_queue() if q["score"] >= 4]
        tickers_opp = [q["ticker"] for q in opportunites[:5]]
        nb_opp_an, nb_opp_open = _analyser_et_trader(tickers_opp, "queue")
        for t in tickers_opp:
            retirer(t)

        # 4. Trade sur la watchlist active (hors positions ouvertes)
        logger.info("📋 ÉTAPE 4 — Analyse watchlist (hors positions ouvertes)")
        from utils.portfolio_db import lire_positions_ouvertes
        ouvertes = {p["ticker"] for p in lire_positions_ouvertes()}
        watchlist_tickers = [t for t in tous_les_tickers(charger_watchlist())
                              if t not in ouvertes][:8]  # limiter à 8 pour rester rapide
        nb_wl_an, nb_wl_open = _analyser_et_trader(watchlist_tickers, "watchlist")

        # 5. Réévaluer les positions ouvertes
        logger.info("🔄 ÉTAPE 5 — Réévaluation positions ouvertes")
        fermes = _reevaluer_positions()

        duree = time.time() - t0
        logger.info("=" * 70)
        logger.info(f"🟡 TACTIQUE — terminé en {duree:.1f}s : "
                    f"{total_dec + total_obs} découvertes/obs, "
                    f"{nb_opp_open + nb_wl_open} ouvert, {fermes} fermé")

        update_heartbeat(CYCLE, status="healthy", duration_sec=duree, extra={
            "decouvertes":  total_dec,
            "observations": total_obs,
            "ouvertures":   nb_opp_open + nb_wl_open,
            "fermetures":   fermes,
            "analyses":     nb_opp_an + nb_wl_an,
        })
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle TACTIQUE échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=time.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
