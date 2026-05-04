"""
agents/paper_trader/portfolio.py — État du portefeuille paper trading
Calcule cash, invested, P&L (réalisé/non-réalisé), total value, mode défensif.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import (
    lire_positions_ouvertes, lire_positions_recentes_fermees, lire_dernier_snapshot,
)

logger = get_logger(__name__)

NB_PERTES_DEFENSIF       = 3   # 3 trades perdants consécutifs → mode défensif
NB_TRADES_DEFENSIF_RESET = 5   # mode défensif désactivé après 5 trades suivants


def prix_actuel(ticker: str) -> float | None:
    """Récupère le prix le plus récent via yfinance (1 req par actif, mis en cache)."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"Prix actuel {ticker} : {e}")
        return None


def est_en_mode_defensif() -> bool:
    """Vrai si les 3 derniers trades fermés sont tous perdants."""
    fermees = lire_positions_recentes_fermees(limite=NB_PERTES_DEFENSIF)
    if len(fermees) < NB_PERTES_DEFENSIF:
        return False
    return all((p.get("pnl_euros") or 0) < 0 for p in fermees)


def risque_par_trade_pct() -> float:
    """Retourne le % de risque par trade (1% en défensif, sinon RISK_PER_TRADE_PCT)."""
    return 1.0 if est_en_mode_defensif() else config.RISK_PER_TRADE_PCT


def seuil_confiance_actuel() -> int:
    """Retourne le seuil de confiance minimum (9 en défensif, sinon ALERT_CONFIDENCE_THRESHOLD)."""
    return 9 if est_en_mode_defensif() else config.ALERT_CONFIDENCE_THRESHOLD


def _enrichir_avec_prix(positions: list[dict], prix_courants: dict[str, float] | None) -> list[dict]:
    """Ajoute prix_actuel + unrealized_pnl à chaque position."""
    if prix_courants is None:
        prix_courants = {}
    for p in positions:
        prix = prix_courants.get(p["ticker"]) or prix_actuel(p["ticker"])
        p["prix_actuel"] = prix
        if prix is None:
            p["unrealized_pnl_euros"] = None
            p["unrealized_pnl_pct"]   = None
            continue
        if p["direction"] == "LONG":
            pnl = (prix - p["entry_price"]) * p["quantity"]
        else:
            pnl = (p["entry_price"] - prix) * p["quantity"]
        p["unrealized_pnl_euros"] = pnl
        p["unrealized_pnl_pct"]   = pnl / p["invested_amount"] * 100 if p["invested_amount"] else 0
    return positions


def etat_portefeuille(prix_courants: dict[str, float] | None = None) -> dict:
    """
    Retourne une vue complète du portefeuille.
    Args : prix_courants pour éviter les appels yfinance répétés (optionnel).
    """
    capital_total = config.CAPITAL
    positions = _enrichir_avec_prix(lire_positions_ouvertes(), prix_courants)

    invested = sum(p["invested_amount"] for p in positions)
    unrealized = sum(p.get("unrealized_pnl_euros") or 0 for p in positions)
    cash = capital_total - invested  # cash effectivement utilisable
    total_value = capital_total + unrealized  # valeur totale incluant gain/perte non-réalisé

    # Performance vs snapshot précédent
    dernier = lire_dernier_snapshot()
    daily_return = ((total_value / dernier["total_value"]) - 1) * 100 if dernier else 0.0

    return {
        "capital_total":           capital_total,
        "capital_investissable":   config.CAPITAL_INVESTISSABLE,
        "cash":                    cash,
        "invested":                invested,
        "unrealized_pnl":          unrealized,
        "total_value":             total_value,
        "open_positions_count":    len(positions),
        "open_positions":          positions,
        "max_positions":           config.MAX_POSITIONS_SIMULTANEES,
        "mode_defensif":           est_en_mode_defensif(),
        "risque_par_trade_pct":    risque_par_trade_pct(),
        "seuil_confiance":         seuil_confiance_actuel(),
        "daily_return_percent":    daily_return,
    }
