"""
utils/indicators.py — Calcul des indicateurs techniques
Indicateurs : RSI, MACD, Bollinger Bands, EMA 20/50/200, ATR, ADX, Stochastic RSI
Source de données : yfinance via la base SQLite ou DataFrame direct
"""

import sys
import os
import sqlite3
import pandas as pd
import pandas_ta as ta
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger   import get_logger
from utils.database import get_connection

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


def calculer_tous_indicateurs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule tous les indicateurs techniques sur un DataFrame OHLCV.
    Retourne le DataFrame enrichi avec les colonnes d'indicateurs.
    """
    if df.empty or len(df) < 50:
        logger.warning("DataFrame trop court pour calculer les indicateurs (min 50 bougies)")
        return df

    def _safe_assign_cols(target_df, source_df, col_map):
        """Assigne des colonnes en cherchant par préfixe (robuste aux variations de nommage)."""
        if source_df is None or source_df.empty:
            return
        for col_target, prefix in col_map.items():
            cols_match = [c for c in source_df.columns if c.startswith(prefix)]
            if cols_match:
                target_df[col_target] = source_df[cols_match[0]]

    # ── RSI (14) ──────────────────────────────────────────────────────────────
    try:
        df["rsi"] = ta.rsi(df["Close"], length=14)
    except Exception as e:
        logger.error(f"RSI : {e}")

    # ── MACD (12, 26, 9) ──────────────────────────────────────────────────────
    try:
        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        _safe_assign_cols(df, macd, {
            "macd":        "MACD_",
            "macd_signal": "MACDs_",
            "macd_hist":   "MACDh_",
        })
    except Exception as e:
        logger.error(f"MACD : {e}")

    # ── Bollinger Bands (20, 2) ───────────────────────────────────────────────
    try:
        bb = ta.bbands(df["Close"], length=20, std=2)
        _safe_assign_cols(df, bb, {
            "bb_upper":  "BBU_",
            "bb_middle": "BBM_",
            "bb_lower":  "BBL_",
        })
    except Exception as e:
        logger.error(f"Bollinger : {e}")

    # ── EMA 20 / 50 / 200 ─────────────────────────────────────────────────────
    try:
        df["ema_20"]  = ta.ema(df["Close"], length=20)
        df["ema_50"]  = ta.ema(df["Close"], length=50)
        df["ema_200"] = ta.ema(df["Close"], length=200)
    except Exception as e:
        logger.error(f"EMA : {e}")

    # ── ATR (14) ──────────────────────────────────────────────────────────────
    try:
        df["atr"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    except Exception as e:
        logger.error(f"ATR : {e}")

    # ── ADX (14) ──────────────────────────────────────────────────────────────
    try:
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        _safe_assign_cols(df, adx, {"adx": "ADX_"})
    except Exception as e:
        logger.error(f"ADX : {e}")

    # ── Stochastic RSI ────────────────────────────────────────────────────────
    try:
        stoch_rsi = ta.stochrsi(df["Close"], length=14)
        if stoch_rsi is not None and not stoch_rsi.empty:
            cols = stoch_rsi.columns.tolist()
            df["stoch_rsi_k"] = stoch_rsi[cols[0]]
            if len(cols) > 1:
                df["stoch_rsi_d"] = stoch_rsi[cols[1]]
    except Exception as e:
        logger.error(f"Stochastic RSI : {e}")

    logger.info(f"Indicateurs calculés sur {len(df)} bougies.")
    return df


def detecter_divergence_rsi(df: pd.DataFrame, fenetre: int = 20) -> str:
    """
    Détecte les divergences RSI vs Prix sur les N dernières bougies.
    Retourne : "haussière", "baissière", ou "aucune"
    """
    try:
        if "rsi" not in df.columns or len(df) < fenetre:
            return "aucune"

        recents = df.tail(fenetre)
        prix_min_idx = recents["Close"].idxmin()
        prix_max_idx = recents["Close"].idxmax()

        # Divergence haussière : nouveau bas prix mais RSI ne fait pas nouveau bas
        if prix_min_idx == recents.index[-1]:
            rsi_au_precedent_bas = recents["rsi"].iloc[:-5].min()
            if recents["rsi"].iloc[-1] > rsi_au_precedent_bas:
                return "haussière"

        # Divergence baissière : nouveau haut prix mais RSI ne fait pas nouveau haut
        if prix_max_idx == recents.index[-1]:
            rsi_au_precedent_haut = recents["rsi"].iloc[:-5].max()
            if recents["rsi"].iloc[-1] < rsi_au_precedent_haut:
                return "baissière"

        return "aucune"

    except Exception as e:
        logger.error(f"Erreur détection divergence RSI : {e}")
        return "aucune"


def detecter_niveaux_cles(df: pd.DataFrame, nb_niveaux: int = 2) -> dict:
    """
    Détecte les supports et résistances clés sur les 100 dernières bougies.
    Méthode : pivots hauts/bas locaux sur fenêtre de 5 bougies.
    Retourne un dict {"supports": [...], "resistances": [...]}
    """
    try:
        recents = df.tail(100).copy()
        prix_actuel = float(recents["Close"].iloc[-1])

        supports     = []
        resistances  = []

        for i in range(2, len(recents) - 2):
            haut = float(recents["High"].iloc[i])
            bas  = float(recents["Low"].iloc[i])

            # Pivot bas = support potentiel
            if (bas < float(recents["Low"].iloc[i-1]) and
                bas < float(recents["Low"].iloc[i-2]) and
                bas < float(recents["Low"].iloc[i+1]) and
                bas < float(recents["Low"].iloc[i+2])):
                if bas < prix_actuel:
                    supports.append(bas)

            # Pivot haut = résistance potentielle
            if (haut > float(recents["High"].iloc[i-1]) and
                haut > float(recents["High"].iloc[i-2]) and
                haut > float(recents["High"].iloc[i+1]) and
                haut > float(recents["High"].iloc[i+2])):
                if haut > prix_actuel:
                    resistances.append(haut)

        # Garder les N niveaux les plus proches du prix actuel
        supports    = sorted(supports,    reverse=True)[:nb_niveaux]
        resistances = sorted(resistances)[:nb_niveaux]

        return {"supports": supports, "resistances": resistances}

    except Exception as e:
        logger.error(f"Erreur détection niveaux clés : {e}")
        return {"supports": [], "resistances": []}


def interpreter_rsi(rsi: float) -> str:
    """Interprétation textuelle du RSI."""
    if rsi is None or np.isnan(rsi):
        return "N/A"
    if rsi >= 80:
        return f"{rsi:.1f} → Fortement suracheté"
    if rsi >= 70:
        return f"{rsi:.1f} → Suracheté"
    if rsi <= 20:
        return f"{rsi:.1f} → Fortement survendu"
    if rsi <= 30:
        return f"{rsi:.1f} → Survendu"
    if 45 <= rsi <= 55:
        return f"{rsi:.1f} → Neutre"
    if rsi > 55:
        return f"{rsi:.1f} → Zone haussière"
    return f"{rsi:.1f} → Zone baissière"


def interpreter_adx(adx: float) -> str:
    """Interprétation textuelle de l'ADX (force de tendance)."""
    if adx is None or np.isnan(adx):
        return "N/A"
    if adx >= 50:
        return f"{adx:.1f} → Tendance très forte"
    if adx >= 25:
        return f"{adx:.1f} → Tendance établie"
    if adx >= 20:
        return f"{adx:.1f} → Tendance faible"
    return f"{adx:.1f} → Pas de tendance (range)"


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
