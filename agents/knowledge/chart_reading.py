"""
agents/knowledge/chart_reading.py — Lecture multi-timeframe v5.0
Lit un graphique en 5 couches comme le ferait un trader expérimenté.
"""

import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs, detecter_divergence_rsi, detecter_niveaux_cles
from agents.analysts.market_analyst.patterns import detecter_tous_patterns, calculer_fibonacci

logger = get_logger(__name__)


def _phase_marche(df) -> str:
    """Identifie la phase Wyckoff : accumulation, markup, distribution, markdown."""
    if df.empty or len(df) < 50:
        return "indéterminée"
    derniere = df.iloc[-1]
    ema_50  = derniere.get("ema_50")
    ema_200 = derniere.get("ema_200")
    prix    = float(derniere["Close"])
    if ema_50 is None or ema_200 is None:
        return "indéterminée"
    if prix > ema_50 > ema_200:
        return "markup (haussière établie)"
    if prix < ema_50 < ema_200:
        return "markdown (baissière établie)"
    if prix < ema_200 and ema_50 < ema_200:
        return "accumulation possible (sous EMA200, à confirmer)"
    if prix > ema_200 and ema_50 > ema_200 and prix < ema_50:
        return "distribution possible (au-dessus EMA200 mais sous EMA50)"
    return "transition (EMAs non alignées)"


def _tendance_simple(df) -> str:
    """Tendance basée sur higher highs/higher lows."""
    if df.empty or len(df) < 20:
        return "indéterminée"
    recent = df.tail(20)
    highs_first = recent["High"].iloc[:10].max()
    highs_last  = recent["High"].iloc[10:].max()
    lows_first  = recent["Low"].iloc[:10].min()
    lows_last   = recent["Low"].iloc[10:].min()
    if highs_last > highs_first and lows_last > lows_first:
        return "Haussière (HH + HL)"
    if highs_last < highs_first and lows_last < lows_first:
        return "Baissière (LH + LL)"
    return "Range (pas de structure claire)"


def _confluence_score(elements: list[str]) -> int:
    """Compte le nombre d'éléments alignés → niveau de conviction."""
    return min(10, 2 + len(elements))


def analyser_graphique(ticker: str, timeframe: str = "1d") -> dict:
    """
    Analyse en 5 couches : structure → niveaux → patterns → contexte MT → confluence.
    """
    df = charger_ohlcv(ticker, timeframe, limite=500)
    if df.empty:
        return {"erreur": f"Pas de données pour {ticker} [{timeframe}]"}
    df = calculer_tous_indicateurs(df)
    if "rsi" not in df.columns:
        return {"erreur": "Indicateurs non calculables"}

    # Couche 1 : Structure
    structure = {
        "tendance":   _tendance_simple(df),
        "phase":      _phase_marche(df),
        "prix":       float(df["Close"].iloc[-1]),
    }

    # Couche 2 : Niveaux
    niveaux = detecter_niveaux_cles(df)
    fib = calculer_fibonacci(df, lookback=100)
    couche_niveaux = {
        "supports":    niveaux.get("supports", []),
        "resistances": niveaux.get("resistances", []),
        "fib_proche":  fib.get("niveau_proche") if fib else None,
    }

    # Couche 3 : Patterns + divergence
    patterns   = detecter_tous_patterns(df)
    divergence = detecter_divergence_rsi(df)
    couche_patterns = {
        "patterns":   patterns,
        "divergence": divergence,
    }

    # Couche 4 : Multi-timeframe
    df_wk = charger_ohlcv(ticker, "1wk", limite=200)
    if not df_wk.empty:
        df_wk = calculer_tous_indicateurs(df_wk)
        couche_mtf = {"weekly": _tendance_simple(df_wk)}
    else:
        couche_mtf = {"weekly": "indisponible"}

    # Couche 5 : Confluence
    elements_alignes = []
    if structure["tendance"] == "Haussière (HH + HL)":
        elements_alignes.append("tendance haussière structurelle")
    if divergence == "haussière":
        elements_alignes.append("divergence RSI haussière")
    if any("haussier" in p.lower() for p in patterns):
        elements_alignes.append("pattern chartiste haussier")
    if structure["phase"] == "markup (haussière établie)":
        elements_alignes.append("phase markup")
    if couche_mtf["weekly"] == "Haussière (HH + HL)":
        elements_alignes.append("tendance weekly haussière")

    return {
        "ticker":         ticker,
        "timeframe":      timeframe,
        "structure":      structure,
        "niveaux":        couche_niveaux,
        "patterns":       couche_patterns,
        "mtf":            couche_mtf,
        "elements_confluence": elements_alignes,
        "score_confluence":    _confluence_score(elements_alignes),
    }
