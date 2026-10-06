"""
agents/paper_trader/monitor.py — Surveillance des positions ouvertes
Vérifie pour chaque position si stop-loss ou take-profit a été touché et ferme.
Tourne au début de chaque routine quotidienne.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.portfolio_db import lire_positions_ouvertes
from agents.paper_trader.portfolio import prix_actuel
from agents.paper_trader.executor import fermer_position
from agents.paper_trader.lockin import lister_lockin, desactiver_lockin
from utils.registre_cycles import noter_cloture, noter_evenement

logger = get_logger(__name__)


def _verifier_position(pos: dict, passage=None) -> dict | None:
    """
    Vérifie SL et TP sur une position. Retourne le résultat de fermeture si touché.
    Logique : sur 1 jour, on ne sait pas si SL ou TP a été touché en 1er.
    Convention prudente : si LOW <= SL → SL touché en priorité (pessimiste).
    Pour V1 simple : on compare au prix de clôture actuel.
    """
    prix = prix_actuel(pos["ticker"])
    if prix is None:
        logger.warning(f"Prix indispo pour {pos['ticker']} — surveillance skippée")
        return None

    direction = pos["direction"]
    sl, tp1, tp2 = pos["stop_loss"], pos["target_1"], pos.get("target_2")

    # v5.5.1 — Trailing stop (opt-in, s'active en amont via API)
    if pos.get("trailing_stop_active"):
        try:
            from agents.technical_skills.trailing_stop import (
                mettre_a_jour_trailing_stop, touche_trailing,
            )
            maj = mettre_a_jour_trailing_stop(pos, prix)
            if maj:
                pos["trailing_stop_price"] = maj["nouveau"]
                logger.info(f"Trailing {pos['ticker']} #{pos['id']} : "
                            f"{maj['ancien']} → {maj['nouveau']} (Δ {maj['delta']:+.4f})")
                noter_evenement(passage, pos, "STOP_DEPLACE", prix,  # registre (Phase 4, R2)
                                {"ancien": maj["ancien"], "nouveau": maj["nouveau"]})
            if touche_trailing(pos, prix):
                ts_val = pos.get("trailing_stop_price")
                op = "≤" if direction == "LONG" else "≥"
                return fermer_position(
                    pos["id"], prix,
                    f"Trailing stop touché ({prix:.4f} {op} {ts_val:.4f})",
                    "CLOSED_TRAILING",
                )
        except Exception as e:
            logger.warning(f"Trailing stop {pos['ticker']} : {e}")

    if direction == "LONG":
        if prix <= sl:
            return fermer_position(pos["id"], prix, f"Stop-loss touché ({prix:.4f} ≤ {sl:.4f})", "CLOSED_SL")
        if tp2 is not None and prix >= tp2:
            return fermer_position(pos["id"], prix, f"Target 2 atteint ({prix:.4f} ≥ {tp2:.4f})", "CLOSED_TP")
        if prix >= tp1:
            return fermer_position(pos["id"], prix, f"Target 1 atteint ({prix:.4f} ≥ {tp1:.4f})", "CLOSED_TP")
    else:  # SHORT
        if prix >= sl:
            return fermer_position(pos["id"], prix, f"Stop-loss touché ({prix:.4f} ≥ {sl:.4f})", "CLOSED_SL")
        if tp2 is not None and prix <= tp2:
            return fermer_position(pos["id"], prix, f"Target 2 atteint ({prix:.4f} ≤ {tp2:.4f})", "CLOSED_TP")
        if prix <= tp1:
            return fermer_position(pos["id"], prix, f"Target 1 atteint ({prix:.4f} ≤ {tp1:.4f})", "CLOSED_TP")
    return None


def monitorer_positions(passage=None) -> dict:
    """
    Vérifie toutes les positions ouvertes. Les positions en LOCK-IN sont vérifiées EN PREMIER.
    Après fermeture, le LOCK-IN éventuel est désactivé.
    passage (Phase 4, R2) : passage du registre du cycle appelant ; clôtures et stops
    déplacés y sont enregistrés (None : rien n'est enregistré).
    """
    positions = lire_positions_ouvertes()
    if not positions:
        logger.info("Monitor : aucune position ouverte à surveiller")
        return {"verifiees": 0, "fermees_tp": 0, "fermees_sl": 0, "details": [], "lockin_actifs": 0}

    # Tickers en LOCK-IN à prioriser
    lockin_tickers = {it["asset"] for it in lister_lockin()}

    # Trier : LOCK-IN d'abord, le reste ensuite
    positions_triees = sorted(positions, key=lambda p: 0 if p["ticker"] in lockin_tickers else 1)

    fermes_tp, fermes_sl, details = 0, 0, []
    for p in positions_triees:
        try:
            res = _verifier_position(p, passage)
        except Exception as e:
            logger.error(f"Monitor erreur sur position #{p['id']} ({p['ticker']}) : {e}")
            continue
        if res is None:
            continue
        noter_cloture(passage, p, "suivi")  # registre (Phase 4, R2) : statut et P&L relus en base
        details.append({
            "ticker":    p["ticker"],
            "pnl_euros": res["pnl_euros"],
            "pnl_percent": res["pnl_percent"],
            "lockin":    p["ticker"] in lockin_tickers,
        })
        if res["pnl_euros"] >= 0:
            fermes_tp += 1
        else:
            fermes_sl += 1
        # Désactiver le LOCK-IN si la position fermée en avait un
        if p["ticker"] in lockin_tickers:
            desactiver_lockin(p["ticker"])

    logger.info(f"Monitor : {len(positions)} surveillée(s) ({len(lockin_tickers)} en LOCK-IN), "
                f"{fermes_tp} TP, {fermes_sl} SL")
    return {
        "verifiees":     len(positions),
        "fermees_tp":    fermes_tp,
        "fermees_sl":    fermes_sl,
        "details":       details,
        "lockin_actifs": len(lockin_tickers),
    }
