"""
agents/sentiment_analyst/analyst.py — Sous-agent 3 : Sentiment Analyst
Évalue le sentiment global du marché et les sentiments spécifiques aux actifs.
Intègre Fear & Greed, news, corrélations BTC/SPY.
"""

import sys
import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import config
from utils.logger   import get_logger
from utils.database import get_connection
from agents.analysts.sentiment_analyst.news_fetcher import resume_news, recuperer_news
from agents.analysts.sentiment_analyst.geopolitics  import resume_contexte_geopolitique
from agents.analysts.sentiment_analyst._llm         import (
    synthese_news_actif, narratif_geopolitique, narratif_global,
)
from agents.analysts.fundamental_analyst.onchain    import recuperer_dominance_btc

logger = get_logger(__name__)

FEAR_GREED_CRYPTO_URL = "https://api.alternative.me/fng/?limit=1"


def recuperer_fear_greed_crypto() -> dict:
    """Récupère le Fear & Greed Index crypto."""
    try:
        r = requests.get(FEAR_GREED_CRYPTO_URL, timeout=10)
        r.raise_for_status()
        data = r.json()["data"][0]
        return {"valeur": int(data["value"]), "label": data["value_classification"]}
    except Exception as e:
        logger.error(f"Erreur Fear & Greed crypto : {e}")
        return {"valeur": None, "label": "Indisponible"}


def charger_prix_bdd(ticker: str, timeframe: str, limite: int = 60) -> pd.Series:
    """Charge les N derniers prix de clôture depuis la BDD en pd.Series."""
    try:
        conn = get_connection()
        df = pd.read_sql_query("""
            SELECT timestamp, close FROM prices
            WHERE ticker = ? AND timeframe = ?
            ORDER BY timestamp DESC LIMIT ?
        """, conn, params=(ticker, timeframe, limite))
        conn.close()
        df = df.iloc[::-1]  # Ordre chronologique croissant
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.set_index("timestamp")["close"]
    except Exception as e:
        logger.error(f"Erreur chargement prix {ticker} : {e}")
        return pd.Series(dtype=float)


def calculer_correlation(ticker_1: str, ticker_2: str, jours: int = 60) -> float | None:
    """Calcule la corrélation des rendements journaliers entre deux actifs."""
    try:
        p1 = charger_prix_bdd(ticker_1, "1d", jours)
        p2 = charger_prix_bdd(ticker_2, "1d", jours)
        if p1.empty or p2.empty:
            return None

        # Rendements journaliers
        r1 = p1.pct_change().dropna()
        r2 = p2.pct_change().dropna()

        # Aligner les dates (jointure interne)
        aligne = pd.concat([r1, r2], axis=1, join="inner").dropna()
        if len(aligne) < 10:
            return None
        return float(aligne.iloc[:, 0].corr(aligne.iloc[:, 1]))
    except Exception as e:
        logger.error(f"Erreur corrélation {ticker_1}/{ticker_2} : {e}")
        return None


def interpreter_correlation(corr: float | None) -> str:
    """Traduit un coefficient de corrélation en texte."""
    if corr is None:
        return "Indisponible"
    if corr >= 0.7:   return f"{corr:+.2f} — Forte positive (risk-on couplé)"
    if corr >= 0.3:   return f"{corr:+.2f} — Positive modérée"
    if corr >= -0.3:  return f"{corr:+.2f} — Faible (actifs décorrélés)"
    if corr >= -0.7:  return f"{corr:+.2f} — Négative modérée (diversification)"
    return f"{corr:+.2f} — Forte négative (hedge)"


def evaluer_sentiment_global(fg_valeur: int | None) -> tuple[str, bool, int]:
    """
    Évalue le sentiment global à partir du Fear & Greed.
    Retourne (sentiment_texte, signal_contrarian, confiance).
    """
    if fg_valeur is None:
        return "Indéterminé", False, 3

    seuil_bas  = config.FEAR_GREED_EXTREME_LOW
    seuil_haut = config.FEAR_GREED_EXTREME_HIGH

    if fg_valeur < seuil_bas:
        return "Très Bearish (Extreme Fear)", True, 7  # Contrarian BUY
    if fg_valeur < 45:
        return "Bearish (Fear)", False, 6
    if fg_valeur <= 55:
        return "Neutre", False, 4
    if fg_valeur <= seuil_haut:
        return "Bullish (Greed)", False, 6
    return "Très Bullish (Extreme Greed)", True, 7  # Contrarian SELL


def generer_rapport_global() -> str:
    """Génère le rapport de sentiment global du marché (+ narratif Gemini)."""
    fg        = recuperer_fear_greed_crypto()
    dominance = recuperer_dominance_btc()
    corrs = {
        "BTC ↔ SPY": calculer_correlation("BTC-USD", "SPY"),
        "BTC ↔ ETH": calculer_correlation("BTC-USD", "ETH-USD"),
        "BTC ↔ SOL": calculer_correlation("BTC-USD", "SOL-USD"),
    }
    fg_val = fg.get("valeur")
    sentiment, contrarian, confiance = evaluer_sentiment_global(fg_val)

    alerte_extreme = ""
    if fg_val is not None:
        if fg_val < config.FEAR_GREED_EXTREME_LOW:
            alerte_extreme = f"⚠️  ALERTE : F&G < {config.FEAR_GREED_EXTREME_LOW} — signal contrarian d'achat potentiel"
        elif fg_val > config.FEAR_GREED_EXTREME_HIGH:
            alerte_extreme = f"⚠️  ALERTE : F&G > {config.FEAR_GREED_EXTREME_HIGH} — signal contrarian de vente potentiel"

    geo = resume_contexte_geopolitique(nb_news=20)
    if geo.get("actif"):
        cats_str = ", ".join(f"{c}({n})" for c, n in geo["categories"].items())
        actifs_str = ", ".join(geo["actifs_a_surveiller"][:8]) or "—"
        bloc_geo = (f"Contexte géopolitique : {cats_str}\n"
                    f"Actifs à surveiller   : {actifs_str}")
    else:
        bloc_geo = "Contexte géopolitique : aucun événement majeur détecté"

    # v5.3.5 : narratifs Gemini (vides si LLM indispo)
    narratif = narratif_global(fg, dominance, corrs, sentiment, contrarian, geo)
    narratif_geo = narratif_geopolitique(geo)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bloc_narratif    = f"\n📖 Narratif marché : {narratif}\n"      if narratif else ""
    bloc_narratif_geo = f"\n🌍 Narratif géo : {narratif_geo}\n"     if narratif_geo else ""

    rapport = f"""
ANALYSE SENTIMENT — MARCHÉ GLOBAL — {now}
────────────────────────────────────────────────────────────
Fear & Greed Crypto : {fg_val if fg_val is not None else 'N/A'} ({fg['label']})
Dominance BTC       : {f'{dominance:.1f}%' if dominance else 'N/A'}
────────────────────────────────────────────────────────────
Corrélations (60 jours) :
  - BTC ↔ SPY       : {interpreter_correlation(corrs['BTC ↔ SPY'])}
  - BTC ↔ ETH       : {interpreter_correlation(corrs['BTC ↔ ETH'])}
  - BTC ↔ SOL       : {interpreter_correlation(corrs['BTC ↔ SOL'])}
────────────────────────────────────────────────────────────
{bloc_geo}{bloc_narratif_geo}────────────────────────────────────────────────────────────
Sentiment global    : {sentiment}
Signal contrarian   : {'Oui — positions extrêmes' if contrarian else 'Non'}
Confiance           : {confiance}/10
{alerte_extreme}{bloc_narratif}""".strip()
    return rapport


def generer_rapport_actif(ticker: str) -> str:
    """Rapport sentiment d'un actif : news brutes + synthèse Gemini."""
    requete_news = ticker.replace("-USD", "") if "-USD" in ticker else ticker
    news_list = recuperer_news(requete_news, nb_max=5)
    synthese = synthese_news_actif(ticker, news_list)  # v5.3.5
    bloc_synthese = f"\n📖 Synthèse : {synthese}\n" if synthese else ""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rapport = f"""
ANALYSE SENTIMENT — {ticker} — {now}
────────────────────────────────────────────────────────────
News récentes :
{resume_news(requete_news, nb_max=5)}{bloc_synthese}""".strip()
    return rapport


if __name__ == "__main__":
    print("\nAlphaSignal — Sentiment Analyst — Test\n")
    print(generer_rapport_global())
    print("\n")
    print(generer_rapport_actif("BTC-USD"))
    print("\n")
    print(generer_rapport_actif("AAPL"))
