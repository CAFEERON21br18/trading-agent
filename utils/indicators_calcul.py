"""
utils/indicators_calcul.py — Calcul des indicateurs techniques sur un DataFrame OHLCV
(RSI, MACD, Bollinger, EMA 20/50/200, ATR, ADX, Stochastic RSI).
Sorti de utils/indicators.py (règle des 200 lignes) ; indicators.py le réexporte.
"""

import pandas as pd
import pandas_ta as ta

from utils.logger import get_logger

logger = get_logger("utils.indicators")  # même nom de journal qu'avant le découpage


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
