"""
agents/fundamental_analyst/alphavantage.py — Wrapper Alpha Vantage
Récupère ratios (OVERVIEW) et earnings (EARNINGS) pour actions US.
Limite du plan gratuit : 25 req/jour, 5 req/min — délai inter-requêtes respecté.
"""

import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import config
from utils.logger import get_logger

logger = get_logger(__name__)

API_URL = "https://www.alphavantage.co/query"
DELAI_INTER_REQ = 13  # secondes — 5 req/min autorisées, marge de sécurité


def _to_float(v) -> float | None:
    """Convertit une valeur Alpha Vantage en float (tolère None / '-' / '')."""
    if v in (None, "None", "-", ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _appel_av(function: str, symbol: str) -> dict:
    """Appel générique à Alpha Vantage avec gestion des erreurs et du rate-limit."""
    if not config.ALPHA_VANTAGE_KEY:
        logger.warning("Clé Alpha Vantage manquante")
        return {}
    try:
        r = requests.get(API_URL, params={
            "function": function,
            "symbol":   symbol,
            "apikey":   config.ALPHA_VANTAGE_KEY,
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "Information" in data:
            logger.warning(f"Alpha Vantage rate-limit atteint sur {function}/{symbol}")
            return {}
        if "Note" in data:
            logger.warning(f"Alpha Vantage note : {data['Note']}")
            return {}
        return data
    except Exception as e:
        logger.error(f"Erreur Alpha Vantage {function}/{symbol} : {e}")
        return {}


def recuperer_overview(ticker: str) -> dict:
    """Ratios fondamentaux : P/E, EPS, market cap, beta, dividende."""
    data = _appel_av("OVERVIEW", ticker)
    if not data or "Symbol" not in data:
        return {}
    return {
        "nom":        data.get("Name"),
        "secteur":    data.get("Sector"),
        "market_cap": _to_float(data.get("MarketCapitalization")),
        "pe_ratio":   _to_float(data.get("PERatio")),
        "eps":        _to_float(data.get("EPS")),
        "dividende":  _to_float(data.get("DividendYield")),
        "beta":       _to_float(data.get("Beta")),
        "high_52w":   _to_float(data.get("52WeekHigh")),
        "low_52w":    _to_float(data.get("52WeekLow")),
    }


def recuperer_dernier_earning(ticker: str) -> dict:
    """Dernier earning publié + surprise vs consensus (après délai 5/min)."""
    time.sleep(DELAI_INTER_REQ)
    data = _appel_av("EARNINGS", ticker)
    quarters = data.get("quarterlyEarnings", []) if data else []
    if not quarters:
        return {}
    d = quarters[0]
    return {
        "date":         d.get("fiscalDateEnding"),
        "eps_estime":   _to_float(d.get("estimatedEPS")),
        "eps_reporte":  _to_float(d.get("reportedEPS")),
        "surprise_pct": _to_float(d.get("surprisePercentage")),
    }
