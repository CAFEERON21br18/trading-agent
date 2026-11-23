"""
utils/real_price.py — Récupération prix historique + actuel + calibration Revolut (v5.3)
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.database import get_connection
from utils.real_price_yahoo import get_historical_price, get_current_price  # noqa: F401 — réexport

logger = get_logger(__name__)


def calibrate_to_revolut(ticker: str, revolut_price: float, symbole: str = "$") -> dict:
    """Calibre le prix de l'agent sur celui affiché par Revolut ; symbole : devise de cotation."""
    base = get_current_price(ticker)
    agent_price = base.get("price")
    if not agent_price:
        return {"success": False, "error": "Prix agent indisponible"}

    factor = revolut_price / agent_price
    conn = get_connection()
    conn.execute("""
        INSERT INTO price_calibration (ticker, adjustment_factor, agent_price, revolut_price, calibrated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            adjustment_factor=excluded.adjustment_factor,
            agent_price=excluded.agent_price,
            revolut_price=excluded.revolut_price,
            calibrated_at=excluded.calibrated_at
    """, (ticker, factor, agent_price, revolut_price,
          datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    ecart = revolut_price - agent_price
    return {
        "success":           True,
        "agent_price":       round(agent_price, 4),
        "revolut_price":     revolut_price,
        "adjustment_factor": round(factor, 5),
        "note":              f"Écart de {abs(ecart):.2f}{symbole} ({(factor-1)*100:+.2f}%) corrigé",
    }


def get_calibration(ticker: str) -> dict | None:
    """Retourne le facteur d'ajustement Revolut s'il existe pour ce ticker."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM price_calibration WHERE ticker = ?", (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_adjusted_price(ticker: str) -> dict:
    """Prix actuel AVEC facteur de calibration Revolut si configuré."""
    base = get_current_price(ticker)
    if not base.get("price"):
        return base
    cal = get_calibration(ticker)
    if cal and cal.get("adjustment_factor"):
        base["price_raw"]  = base["price"]
        base["price"]      = round(base["price"] * cal["adjustment_factor"], 4)
        base["calibrated"] = True
        base["adjustment_factor"] = cal["adjustment_factor"]
    else:
        base["calibrated"] = False
    return base


def prix_actuel_brut(ticker: str) -> float | None:
    """Helper simple : prix BRUT (non calibré) — référence pour le calcul du P&L."""
    r = get_current_price(ticker)
    return r.get("price")


def calculate_position_pnl(investment: dict, current_raw: float | None = None) -> dict | None:
    """
    v5.3.1 — Calcul P&L CORRECT : prix bruts cohérents (entrée brute + actuel brut).
    La calibration n'est utilisée que pour l'AFFICHAGE des prix unitaires.

    Math : le facteur s'annule dans le ratio → le % est identique en raw ou calibré.
    On garde le raw pour le calcul, et on affiche des prix calibrés pour la lisibilité.
    """
    ticker     = investment["asset"]
    entry_raw  = investment["entry_price"]
    quantity   = investment["quantity"]
    invested   = investment["invested_amount"]
    direction  = investment.get("direction", "LONG")

    if current_raw is None:
        info = get_current_price(ticker)
        current_raw = info.get("price")
        source = info.get("source")
    else:
        source = "cache"
    if not current_raw:
        return None

    # P&L : tout en prix BRUTS → cohérent et mathématiquement exact
    if direction == "LONG":
        pnl_euros = (current_raw - entry_raw) * quantity
    else:
        pnl_euros = (entry_raw - current_raw) * quantity
    pnl_percent   = (pnl_euros / invested * 100) if invested else 0.0
    current_value = invested + pnl_euros

    # Affichage : prix calibrés (pour ressembler à Revolut visuellement)
    cal = get_calibration(ticker)
    factor = cal["adjustment_factor"] if cal else 1.0
    entry_display   = round(entry_raw   * factor, 4)
    current_display = round(current_raw * factor, 4)

    return {
        "current_price_raw":      round(current_raw, 4),
        "current_price_display":  current_display,
        "entry_price_raw":        round(entry_raw, 4),
        "entry_price_display":    entry_display,
        "pnl_euros":              round(pnl_euros, 2),
        "pnl_percent":            round(pnl_percent, 2),
        "current_value":          round(current_value, 2),
        "calibrated":             cal is not None,
        "adjustment_factor":      factor,
        "source":                 source,
    }
