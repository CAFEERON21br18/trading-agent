"""
agents/explorers/crypto_explorer/universe.py — Univers : top N cryptos par market cap (CoinGecko)
Cache 1h pour éviter le rate-limit gratuit (50 req/min, 10k/mois).
Exclut stablecoins et wrapped tokens.
"""

import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger
from utils.cache import avec_cache

logger = get_logger(__name__)

URL = "https://api.coingecko.com/api/v3/coins/markets"
EXCLUS = {
    # stablecoins
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDD", "FRAX", "USDP", "FDUSD", "PYUSD",
    "GUSD", "LUSD", "UST", "EURT", "EURS",
    # wrapped tokens
    "WBTC", "WETH", "STETH", "WSTETH", "WBETH", "RETH", "CBETH",
}


def _fetch_top(nb: int) -> list[dict]:
    """Récupère le top nb cryptos depuis CoinGecko (cache 1h)."""
    def fetch():
        params = {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": min(nb, 250), "page": 1, "sparkline": "false",
        }
        r = requests.get(URL, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    return avec_cache("coingecko_top", f"top_{nb}", fetch) or []


def _to_yfinance_ticker(symbol: str) -> str:
    """Transforme un symbole CoinGecko (ex: 'btc') en ticker yfinance ('BTC-USD')."""
    return f"{symbol.upper()}-USD"


def lister_univers(nb_max: int = 50) -> list[str]:
    """
    Retourne la liste des tickers crypto au format yfinance, hors stablecoins/wrapped.
    """
    items = _fetch_top(nb_max + len(EXCLUS))  # marge pour exclusions
    tickers = []
    for c in items:
        symbol = (c.get("symbol") or "").upper()
        if symbol in EXCLUS or not symbol:
            continue
        tickers.append(_to_yfinance_ticker(symbol))
        if len(tickers) >= nb_max:
            break
    return tickers


def metadata_univers(nb_max: int = 50) -> dict[str, dict]:
    """Retourne {ticker: {market_cap, volume_24h, variation_24h}} pour le filtrage."""
    items = _fetch_top(nb_max + len(EXCLUS))
    meta = {}
    for c in items:
        symbol = (c.get("symbol") or "").upper()
        if symbol in EXCLUS or not symbol:
            continue
        meta[_to_yfinance_ticker(symbol)] = {
            "nom":             c.get("name"),
            "market_cap":      c.get("market_cap") or 0,
            "volume_24h":      c.get("total_volume") or 0,
            "variation_24h":   c.get("price_change_percentage_24h") or 0,
            "ath_change_pct":  c.get("ath_change_percentage") or 0,
            "rank":            c.get("market_cap_rank"),
        }
        if len(meta) >= nb_max:
            break
    return meta
