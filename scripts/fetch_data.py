"""
scripts/fetch_data.py — Collecte de données de marché
Sources : yfinance (actions/ETF/indices), CoinGecko (crypto), Fear & Greed Index
Usage : python3 scripts/fetch_data.py
"""

import sys
import os
import time
import requests
import yfinance as yf
import pandas as pd

# Ajout du dossier racine au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger   import get_logger
from utils.database import initialiser_base, sauvegarder_prix
from utils.helpers  import charger_watchlist, formater_prix, timestamp_maintenant

logger = get_logger(__name__)

# Mapping timeframe watchlist → paramètres yfinance
TIMEFRAME_CONFIG = {
    "1d":  {"period": "2y",  "interval": "1d"},
    "1wk": {"period": "5y",  "interval": "1wk"},
    "4h":  {"period": "60d", "interval": "1h"},  # yfinance n'a pas de 4H natif
}

# URL de l'API Fear & Greed Index (gratuite, sans clé)
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"

# URL CoinGecko (gratuite, sans clé) — données de marché crypto
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_IDS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
}


def recuperer_ohlcv_yfinance(ticker: str, timeframe: str) -> pd.DataFrame:
    """
    Récupère les données OHLCV via yfinance.
    Retourne un DataFrame vide en cas d'erreur.
    """
    config = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
    try:
        logger.info(f"Téléchargement {ticker} [{timeframe}]...")
        df = yf.download(
            ticker,
            period=config["period"],
            interval=config["interval"],
            auto_adjust=True,
            progress=False,
        )

        if df.empty:
            logger.warning(f"Aucune donnée reçue pour {ticker} [{timeframe}]")
            return pd.DataFrame()

        # Nettoyage des colonnes multi-index (yfinance peut en générer)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        logger.info(f"{ticker} [{timeframe}] : {len(df)} bougies récupérées.")
        return df

    except Exception as e:
        logger.error(f"Erreur yfinance {ticker} [{timeframe}] : {e}")
        return pd.DataFrame()


def recuperer_fear_greed() -> dict:
    """
    Récupère le Fear & Greed Index crypto depuis alternative.me.
    Retourne un dict avec value et value_classification.
    """
    try:
        response = requests.get(FEAR_GREED_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        valeur = int(data["data"][0]["value"])
        label  = data["data"][0]["value_classification"]
        logger.info(f"Fear & Greed Index : {valeur} ({label})")
        return {"valeur": valeur, "label": label}
    except Exception as e:
        logger.error(f"Erreur Fear & Greed API : {e}")
        return {"valeur": None, "label": "Indisponible"}


def recuperer_prix_coingecko(ticker: str) -> float | None:
    """
    Récupère le prix actuel d'un actif crypto via CoinGecko.
    Retourne None en cas d'erreur.
    """
    coin_id = COINGECKO_IDS.get(ticker)
    if not coin_id:
        return None
    try:
        params = {"ids": coin_id, "vs_currencies": "usd"}
        response = requests.get(COINGECKO_URL, params=params, timeout=10)
        response.raise_for_status()
        data   = response.json()
        prix   = data[coin_id]["usd"]
        logger.info(f"CoinGecko {ticker} : ${formater_prix(prix)}")
        return prix
    except Exception as e:
        logger.error(f"Erreur CoinGecko {ticker} : {e}")
        return None


def collecter_toute_la_watchlist(watchlist: dict) -> dict:
    """
    Collecte les données OHLCV de toute la watchlist et les sauvegarde en BDD.
    Retourne un résumé {ticker: {timeframe: nb_lignes}}.
    """
    resume = {}

    for categorie, actifs in watchlist.items():
        for ticker, info in actifs.items():
            resume[ticker] = {}
            timeframes = info.get("timeframes", ["1d"])

            for tf in timeframes:
                df = recuperer_ohlcv_yfinance(ticker, tf)
                if not df.empty:
                    nb = sauvegarder_prix(ticker, tf, df)
                    resume[ticker][tf] = nb
                else:
                    resume[ticker][tf] = 0

                # Pause courte pour ne pas surcharger l'API
                time.sleep(0.5)

    return resume


def afficher_resume(ticker: str, timeframe: str = "1d", nb_lignes: int = 5):
    """Affiche les N dernières bougies d'un actif pour vérification."""
    try:
        df = yf.download(ticker, period="10d", interval=timeframe,
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty:
            print(f"Aucune donnée pour {ticker}")
            return

        print(f"\n{'='*60}")
        print(f"  {ticker} [{timeframe}] — {nb_lignes} dernières bougies")
        print(f"  Données au : {timestamp_maintenant()}")
        print(f"{'='*60}")
        print(df[["Open","High","Low","Close","Volume"]].tail(nb_lignes).to_string())
        print()

    except Exception as e:
        logger.error(f"Erreur affichage {ticker} : {e}")


if __name__ == "__main__":
    print("\nAlphaSignal — Collecte de données\n")

    # Initialisation de la base
    initialiser_base()

    # Chargement de la watchlist
    watchlist = charger_watchlist()
    if not watchlist:
        print("Watchlist vide ou introuvable. Vérifie data/watchlist.json")
        sys.exit(1)

    # Fear & Greed Index
    print("--- Fear & Greed Index ---")
    fg = recuperer_fear_greed()
    print(f"Valeur : {fg['valeur']} — {fg['label']}\n")

    # Test rapide : afficher les 5 dernières bougies de BTC et AAPL
    print("--- Aperçu des données (5 dernières bougies) ---")
    afficher_resume("BTC-USD", "1d", 5)
    afficher_resume("AAPL",    "1d", 5)

    # Collecte complète de la watchlist
    print("\n--- Collecte complète de la watchlist ---")
    resume = collecter_toute_la_watchlist(watchlist)

    print("\n--- Résumé de la collecte ---")
    for ticker, tfs in resume.items():
        for tf, nb in tfs.items():
            statut = "✅" if nb > 0 else "⚠️ "
            print(f"  {statut} {ticker:12s} [{tf}] : {nb} nouvelles lignes")

    print("\nCollecte terminée.")
