"""
agents/backtester/engine.py — Moteur de backtesting + 5 stratégies classiques
Stratégies : EMA 20/50, EMA 50/200, RSI+EMA200, Bollinger mean reversion, MACD+ADX
"""

import sys
import os
import pandas as pd
import numpy as np
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger     import get_logger
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs
from agents.backtester.metrics import calculer_metriques, formater_metriques

logger = get_logger(__name__)

FRAIS_PAR_TRADE = 0.001  # 0.1% par trade (approximation Revolut)


# ═══════════════════════════════════════════════════════════════════════════════
# STRATÉGIES — chacune retourne une Series de signaux : +1 (LONG), -1 (SHORT), 0 (FLAT)
# ═══════════════════════════════════════════════════════════════════════════════

def strategie_ema_20_50(df: pd.DataFrame) -> pd.Series:
    """Croisement EMA 20/50 : long quand EMA20 > EMA50, flat sinon."""
    signal = pd.Series(0, index=df.index)
    signal[df["ema_20"] > df["ema_50"]] = 1
    return signal


def strategie_ema_50_200(df: pd.DataFrame) -> pd.Series:
    """Golden Cross / Death Cross : EMA 50/200."""
    signal = pd.Series(0, index=df.index)
    signal[df["ema_50"] > df["ema_200"]] = 1
    return signal


def strategie_rsi_trend(df: pd.DataFrame) -> pd.Series:
    """RSI oversold/overbought + filtre tendance EMA200."""
    signal = pd.Series(0, index=df.index)
    tendance_haussiere = df["Close"] > df["ema_200"]
    tendance_baissiere = df["Close"] < df["ema_200"]
    # LONG : RSI < 35 ET tendance haussière
    signal[(df["rsi"] < 35) & tendance_haussiere] = 1
    # Sortie quand RSI > 65
    return signal


def strategie_bollinger_reversion(df: pd.DataFrame) -> pd.Series:
    """Mean reversion : long quand prix touche bande inf ET RSI < 30."""
    signal = pd.Series(0, index=df.index)
    signal[(df["Close"] < df["bb_lower"]) & (df["rsi"] < 30)] = 1
    # Sortie : retour à la moyenne (implicit via prochain signal 0)
    signal[df["Close"] > df["bb_middle"]] = 0
    return signal


def strategie_macd_adx(df: pd.DataFrame) -> pd.Series:
    """MACD crossover avec filtre ADX > 25 (tendance forte)."""
    signal = pd.Series(0, index=df.index)
    macd_haussier = df["macd"] > df["macd_signal"]
    tendance_forte = df["adx"] > 25
    signal[macd_haussier & tendance_forte] = 1
    return signal


STRATEGIES = {
    "EMA 20/50":             strategie_ema_20_50,
    "EMA 50/200 (Golden)":   strategie_ema_50_200,
    "RSI + EMA200 filter":   strategie_rsi_trend,
    "Bollinger reversion":   strategie_bollinger_reversion,
    "MACD + ADX>25":         strategie_macd_adx,
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOTEUR DE BACKTEST
# ═══════════════════════════════════════════════════════════════════════════════

def run_backtest(df: pd.DataFrame, strategie_fn: Callable,
                 capital_initial: float = 1000) -> tuple[list, pd.Series]:
    """
    Exécute un backtest simple : entrée au prochain open après signal, exit quand signal=0.
    Frais 0.1% par trade appliqués à l'entrée et à la sortie.
    Retourne (liste_trades, equity_curve).
    """
    if df.empty or len(df) < 200:
        return [], pd.Series(dtype=float)

    signaux = strategie_fn(df).fillna(0)

    capital = capital_initial
    position_ouverte = False
    entry_price = 0
    entry_date  = None
    trades = []
    equity = []

    for i in range(len(df) - 1):
        date   = df.index[i]
        signal = signaux.iloc[i]
        prix_close = float(df["Close"].iloc[i])

        # Mise à jour equity (valeur portefeuille courante)
        if position_ouverte:
            valeur_courante = capital * (prix_close / entry_price)
            equity.append((date, valeur_courante))
        else:
            equity.append((date, capital))

        # Gestion des ordres (exécutés au prochain open)
        prochain_open = float(df["Open"].iloc[i + 1])

        if not position_ouverte and signal == 1:
            # Entrée LONG
            entry_price = prochain_open * (1 + FRAIS_PAR_TRADE)
            entry_date  = df.index[i + 1]
            position_ouverte = True

        elif position_ouverte and signal == 0:
            # Exit
            exit_price = prochain_open * (1 - FRAIS_PAR_TRADE)
            pnl_pct    = (exit_price - entry_price) / entry_price * 100
            pnl_eur    = capital * (pnl_pct / 100)
            capital    = capital + pnl_eur
            trades.append({
                "entry_date":  entry_date,
                "exit_date":   df.index[i + 1],
                "direction":   "LONG",
                "entry_price": entry_price,
                "exit_price":  exit_price,
                "pnl":         pnl_eur,
                "pnl_pct":     pnl_pct,
            })
            position_ouverte = False

    # Si encore en position à la fin, on ferme au dernier close
    if position_ouverte:
        derniere_close = float(df["Close"].iloc[-1]) * (1 - FRAIS_PAR_TRADE)
        pnl_pct        = (derniere_close - entry_price) / entry_price * 100
        pnl_eur        = capital * (pnl_pct / 100)
        capital        = capital + pnl_eur
        trades.append({
            "entry_date":  entry_date,
            "exit_date":   df.index[-1],
            "direction":   "LONG",
            "entry_price": entry_price,
            "exit_price":  derniere_close,
            "pnl":         pnl_eur,
            "pnl_pct":     pnl_pct,
        })

    equity.append((df.index[-1], capital))
    equity_series = pd.Series({d: v for d, v in equity})
    return trades, equity_series


def rendement_buy_and_hold(df: pd.DataFrame) -> float:
    """Calcule le rendement Buy & Hold sur la période (%)."""
    if df.empty or len(df) < 2:
        return 0
    return (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[0])) / float(df["Close"].iloc[0]) * 100


def tester_toutes_strategies(ticker: str, timeframe: str = "1d",
                              capital_initial: float = 1000) -> list[dict]:
    """Lance les 5 stratégies sur un actif, retourne les résultats classés par rendement."""
    df = charger_ohlcv(ticker, timeframe, limite=1000)
    if df.empty:
        logger.error(f"Pas de données pour {ticker} [{timeframe}]")
        return []

    df = calculer_tous_indicateurs(df).dropna().copy()
    if len(df) < 250:
        logger.warning(f"{ticker} : seulement {len(df)} bougies après dropna — résultats peu fiables")

    bh_pct = rendement_buy_and_hold(df)
    resultats = []

    for nom, fn in STRATEGIES.items():
        trades, equity = run_backtest(df, fn, capital_initial)
        metriques = calculer_metriques(trades, equity, capital_initial)
        resultats.append({
            "nom_strategie":  nom,
            "ticker":         ticker,
            "metriques":      metriques,
            "rendement_bh":   bh_pct,
            "trades":         trades,
            "equity":         equity,
        })

    resultats.sort(key=lambda r: r["metriques"]["rendement_total_pct"], reverse=True)
    return resultats


if __name__ == "__main__":
    print("\nAlphaSignal — Backtester — Test\n")

    for ticker in ["BTC-USD", "AAPL"]:
        print(f"\n{'='*60}")
        print(f"  BACKTEST : {ticker} — Daily — 5 stratégies")
        print(f"{'='*60}")

        resultats = tester_toutes_strategies(ticker, "1d")
        for r in resultats:
            print(f"\n{formater_metriques(r['metriques'], r['nom_strategie'], r['ticker'], r['rendement_bh'])}")

        if resultats:
            meilleure = resultats[0]
            print(f"\n🏆 Meilleure stratégie pour {ticker} : {meilleure['nom_strategie']} "
                  f"({meilleure['metriques']['rendement_total_pct']:+.2f}%)")
