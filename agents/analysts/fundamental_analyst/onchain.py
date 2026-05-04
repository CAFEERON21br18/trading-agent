"""
agents/fundamental_analyst/onchain.py — Données fondamentales crypto via CoinGecko
API gratuite sans clé : market cap, volume 24h, variations, dominance BTC
"""

import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger

logger = get_logger(__name__)

COINGECKO_API = "https://api.coingecko.com/api/v3"

# Mapping ticker watchlist → id CoinGecko
TICKER_TO_COINGECKO = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
}


def recuperer_donnees_coin(ticker: str) -> dict:
    """
    Récupère les données fondamentales d'un crypto depuis CoinGecko.
    Retourne un dict avec : market_cap, volume_24h, variation_24h, variation_7j, variation_30j, ath_distance
    """
    coin_id = TICKER_TO_COINGECKO.get(ticker)
    if not coin_id:
        return {}

    try:
        url = f"{COINGECKO_API}/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers":      "false",
            "market_data":  "true",
            "community_data": "false",
            "developer_data": "false",
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        md = data.get("market_data", {})

        def _get_usd(champ: str) -> float | None:
            valeur = md.get(champ, {})
            if isinstance(valeur, dict):
                return valeur.get("usd")
            return valeur

        prix_actuel = _get_usd("current_price")
        ath         = _get_usd("ath")
        distance_ath = ((prix_actuel - ath) / ath * 100) if (prix_actuel and ath) else None

        return {
            "nom":              data.get("name", coin_id),
            "market_cap":       _get_usd("market_cap"),
            "volume_24h":       _get_usd("total_volume"),
            "variation_24h":    md.get("price_change_percentage_24h"),
            "variation_7j":     md.get("price_change_percentage_7d"),
            "variation_30j":    md.get("price_change_percentage_30d"),
            "ath":              ath,
            "distance_ath_pct": distance_ath,
            "rang_market_cap":  md.get("market_cap_rank"),
        }

    except Exception as e:
        logger.error(f"Erreur CoinGecko {ticker} : {e}")
        return {}


def recuperer_dominance_btc() -> float | None:
    """Récupère la dominance BTC (% du market cap crypto total)."""
    try:
        r = requests.get(f"{COINGECKO_API}/global", timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("market_cap_percentage", {}).get("btc")
    except Exception as e:
        logger.error(f"Erreur dominance BTC : {e}")
        return None


def formater_grand_nombre(n: float | None) -> str:
    """Formate un grand nombre (ex: 1_500_000_000 → '1.5Md')."""
    if n is None:
        return "N/A"
    if abs(n) >= 1e12: return f"{n/1e12:.2f}T$"
    if abs(n) >= 1e9:  return f"{n/1e9:.2f}Md$"
    if abs(n) >= 1e6:  return f"{n/1e6:.2f}M$"
    if abs(n) >= 1e3:  return f"{n/1e3:.2f}K$"
    return f"{n:.2f}$"


def formater_pct(p: float | None) -> str:
    """Formate un pourcentage avec signe."""
    if p is None:
        return "N/A"
    return f"{p:+.2f}%"


def evaluer_crypto(donnees: dict, dominance_btc: float | None) -> tuple[str, str, int]:
    """
    Évalue un crypto sur la base de ses fondamentaux.
    Retourne (évaluation, impact_attendu, confiance).
    """
    confiance = 5
    motifs = []

    dist_ath = donnees.get("distance_ath_pct")
    if dist_ath is not None:
        if dist_ath <= -50:
            motifs.append("Fort drawdown depuis ATH (opportunité potentielle)")
            confiance += 1
        elif dist_ath >= -5:
            motifs.append("Proche ATH (risque de correction)")
            confiance -= 1

    var_7j = donnees.get("variation_7j")
    if var_7j is not None and var_7j < -15:
        motifs.append(f"Forte chute 7j ({var_7j:.1f}%)")
    elif var_7j is not None and var_7j > 15:
        motifs.append(f"Forte hausse 7j ({var_7j:.1f}%)")

    # Évaluation qualitative
    if dist_ath is not None and dist_ath <= -40:
        evaluation = "Sous-évalué"
        impact     = "Positif"
    elif dist_ath is not None and dist_ath >= -5:
        evaluation = "Sur-évalué"
        impact     = "Négatif"
    else:
        evaluation = "Juste valeur"
        impact     = "Neutre"

    return evaluation, impact, min(10, max(1, confiance))
