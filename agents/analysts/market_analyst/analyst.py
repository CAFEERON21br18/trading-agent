"""
agents/market_analyst/analyst.py — Sous-agent 1 : Market Analyst (Analyse Technique)
Génère des analyses techniques complètes par actif avec scoring 1-10.
Analyse multi-timeframe : Weekly (contexte) → Daily (signal) → 4H (entrée crypto).
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger     import get_logger
from utils.indicators import (
    charger_ohlcv, calculer_tous_indicateurs,
    detecter_divergence_rsi, detecter_niveaux_cles,
    interpreter_rsi, interpreter_adx,
)
from agents.analysts.market_analyst.patterns import detecter_tous_patterns
from agents.analysts.market_analyst.score import analyser_tendance, calculer_score  # noqa: F401 — réexport

logger = get_logger(__name__)


def analyser_actif(ticker: str, timeframe: str = "1d") -> str:
    """
    Analyse technique complète d'un actif sur un timeframe.
    Retourne le rapport formaté.
    """
    df = charger_ohlcv(ticker, timeframe, limite=500)
    if df.empty:
        return f"❌ Impossible d'analyser {ticker} [{timeframe}] — données absentes"

    df = calculer_tous_indicateurs(df)
    if "rsi" not in df.columns:
        return f"❌ Indicateurs non calculables pour {ticker} [{timeframe}]"

    derniere  = df.iloc[-1]
    prix      = float(derniere["Close"])
    tendance, tendance_justif = analyser_tendance(df)
    score, signal, motifs     = calculer_score(df, tendance)
    patterns                  = detecter_tous_patterns(df)
    niveaux                   = detecter_niveaux_cles(df)

    # Extraction valeurs
    rsi       = derniere.get("rsi")
    macd      = derniere.get("macd")
    macd_sig  = derniere.get("macd_signal")
    adx       = derniere.get("adx")
    bb_upper  = derniere.get("bb_upper")
    bb_middle = derniere.get("bb_middle")
    bb_lower  = derniere.get("bb_lower")
    divergence = detecter_divergence_rsi(df)

    # Formatage bollinger
    if bb_upper is not None and bb_lower is not None:
        if prix > bb_upper:   bb_str = "Au-dessus bande sup (suracheté)"
        elif prix < bb_lower: bb_str = "Sous bande inf (survendu)"
        else:
            pct = (prix - bb_lower) / (bb_upper - bb_lower) * 100
            bb_str = f"Dans les bandes ({pct:.0f}% de la largeur)"
    else:
        bb_str = "N/A"

    macd_str = "Haussier (MACD > Signal)" if (macd and macd_sig and macd > macd_sig) else "Baissier (MACD < Signal)"
    supports_str    = " | ".join([f"{s:,.2f}" for s in niveaux["supports"]]) or "Aucun"
    resistances_str = " | ".join([f"{r:,.2f}" for r in niveaux["resistances"]]) or "Aucune"
    patterns_str    = ", ".join(patterns) if patterns else "Aucun"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rapport = f"""
ANALYSE TECHNIQUE — {ticker} — {now}
Timeframe principal : {timeframe.upper()}
Prix actuel : {prix:,.4f}
Tendance : {tendance} ({tendance_justif})
────────────────────────────────────────────────────────────
Indicateurs clés :
  - RSI(14)        : {interpreter_rsi(float(rsi) if rsi is not None else None)}
  - MACD(12,26,9)  : {macd_str}
  - Bollinger      : {bb_str}
  - ADX(14)        : {interpreter_adx(float(adx) if adx is not None else None)}
Niveaux clés :
  - Supports       : {supports_str}
  - Résistances    : {resistances_str}
Patterns          : {patterns_str}
Divergences RSI   : {divergence.capitalize()}
────────────────────────────────────────────────────────────
SIGNAL   : {signal}
CONFIANCE: {score}/10
Justification :
""" + "\n".join(f"  • {m}" for m in motifs) + "\n"
    return rapport.strip()


def analyse_multi_timeframe(ticker: str, timeframes: list[str]) -> str:
    """Génère une analyse pour chaque timeframe et les concatène."""
    rapports = []
    for tf in timeframes:
        rapports.append(analyser_actif(ticker, tf))
    return "\n\n".join(rapports)


if __name__ == "__main__":
    print("\nAlphaSignal — Market Analyst — Test\n")
    print(analyser_actif("BTC-USD", "1d"))
    print("\n")
    print(analyser_actif("AAPL", "1d"))
    print("\n")
    print("=== Multi-timeframe BTC (Weekly + Daily + 4H) ===\n")
    print(analyse_multi_timeframe("BTC-USD", ["1wk", "1d", "4h"]))
