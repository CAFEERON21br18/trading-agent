"""
utils/indicators.py — Calcul des indicateurs techniques
Indicateurs : RSI, MACD, Bollinger Bands, EMA 20/50/200, ATR, ADX, Stochastic RSI
Source de données : yfinance via la base SQLite ou DataFrame direct
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger   import get_logger
from utils.database import get_connection
from utils.indicators_calcul import calculer_tous_indicateurs  # noqa: F401 — réexport
from utils.indicators_lecture import (  # noqa: F401 — réexport
    detecter_divergence_rsi, detecter_niveaux_cles, interpreter_rsi, interpreter_adx,
)

logger = get_logger(__name__)


def charger_ohlcv(ticker: str, timeframe: str, limite: int = 500) -> pd.DataFrame:
    """
    Charge les données OHLCV depuis la base SQLite locale.
    Retourne un DataFrame propre avec colonnes Open/High/Low/Close/Volume.
    """
    try:
        conn = get_connection()
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM prices
            WHERE ticker = ? AND timeframe = ?
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn, params=(ticker, timeframe))
        conn.close()

        if df.empty:
            logger.warning(f"Aucune donnée en BDD pour {ticker} [{timeframe}] — lance d'abord scripts/fetch_data.py")
            return pd.DataFrame()

        # Renommer pour cohérence avec pandas-ta (attend Open, High, Low, Close, Volume)
        df.rename(columns={
            "open":   "Open",
            "high":   "High",
            "low":    "Low",
            "close":  "Close",
            "volume": "Volume",
        }, inplace=True)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df = df.tail(limite)
        return df

    except Exception as e:
        logger.error(f"Erreur chargement OHLCV {ticker} [{timeframe}] : {e}")
        return pd.DataFrame()


def resume_indicateurs(ticker: str, timeframe: str = "1d") -> str:
    """
    Génère un résumé textuel de tous les indicateurs pour un actif.
    Utilisé par le Market Analyst pour construire ses rapports.
    """
    df = charger_ohlcv(ticker, timeframe)
    if df.empty:
        return f"Impossible de charger les données pour {ticker}"

    df = calculer_tous_indicateurs(df)
    derniere = df.iloc[-1]
    prix     = float(derniere["Close"])

    # Valeurs des indicateurs
    rsi        = derniere.get("rsi")
    macd       = derniere.get("macd")
    macd_sig   = derniere.get("macd_signal")
    bb_upper   = derniere.get("bb_upper")
    bb_lower   = derniere.get("bb_lower")
    ema_20     = derniere.get("ema_20")
    ema_50     = derniere.get("ema_50")
    ema_200    = derniere.get("ema_200")
    atr        = derniere.get("atr")
    adx        = derniere.get("adx")

    # Divergences et niveaux
    divergence = detecter_divergence_rsi(df)
    niveaux    = detecter_niveaux_cles(df)

    # Alignement EMA
    if all(v is not None and not np.isnan(v) for v in [ema_20, ema_50, ema_200]):
        if prix > ema_20 > ema_50 > ema_200:
            alignement_ema = "Haussier (prix > EMA20 > EMA50 > EMA200)"
        elif prix < ema_20 < ema_50 < ema_200:
            alignement_ema = "Baissier (prix < EMA20 < EMA50 < EMA200)"
        else:
            alignement_ema = "Mixte / Neutre"
    else:
        alignement_ema = "N/A (données insuffisantes)"

    # Signal MACD
    if macd is not None and macd_sig is not None:
        signal_macd = "Haussier (MACD > Signal)" if macd > macd_sig else "Baissier (MACD < Signal)"
    else:
        signal_macd = "N/A"

    # Position Bollinger
    if bb_upper is not None and bb_lower is not None:
        if prix > bb_upper:
            pos_bb = "Au-dessus de la bande supérieure (suracheté potentiel)"
        elif prix < bb_lower:
            pos_bb = "En dessous de la bande inférieure (survendu potentiel)"
        else:
            bande_pct = (prix - bb_lower) / (bb_upper - bb_lower) * 100
            pos_bb = f"Dans les bandes ({bande_pct:.0f}% de la largeur)"
    else:
        pos_bb = "N/A"

    supports_str    = " | ".join([f"{s:,.2f}" for s in niveaux["supports"]]) or "Aucun détecté"
    resistances_str = " | ".join([f"{r:,.2f}" for r in niveaux["resistances"]]) or "Aucune détectée"

    resume = f"""
INDICATEURS TECHNIQUES — {ticker} — [{timeframe.upper()}]
Prix actuel : {prix:,.4f}
{'─'*55}
RSI(14)        : {interpreter_rsi(float(rsi) if rsi is not None else None)}
MACD(12,26,9)  : {signal_macd}
Bollinger(20,2): {pos_bb}
EMA 20/50/200  : {alignement_ema}
ATR(14)        : {f'{float(atr):.4f}' if atr is not None else 'N/A'} (volatilité sur 14 bougies)
ADX(14)        : {interpreter_adx(float(adx) if adx is not None else None)}
{'─'*55}
Supports       : {supports_str}
Résistances    : {resistances_str}
Divergence RSI : {divergence.capitalize()}
"""
    return resume.strip()


if __name__ == "__main__":
    print("\nAlphaSignal — Test des indicateurs techniques\n")
    print(resume_indicateurs("BTC-USD", "1d"))
    print()
    print(resume_indicateurs("AAPL", "1d"))
