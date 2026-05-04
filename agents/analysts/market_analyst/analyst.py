"""
agents/market_analyst/analyst.py — Sous-agent 1 : Market Analyst (Analyse Technique)
Génère des analyses techniques complètes par actif avec scoring 1-10.
Analyse multi-timeframe : Weekly (contexte) → Daily (signal) → 4H (entrée crypto).
"""

import sys
import os
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger     import get_logger
from utils.indicators import (
    charger_ohlcv, calculer_tous_indicateurs,
    detecter_divergence_rsi, detecter_niveaux_cles,
    interpreter_rsi, interpreter_adx,
)
from agents.analysts.market_analyst.patterns import detecter_tous_patterns

logger = get_logger(__name__)


def analyser_tendance(df) -> tuple[str, str]:
    """
    Analyse la tendance via l'alignement des EMA.
    Retourne (direction, justification).
    """
    derniere = df.iloc[-1]
    prix     = float(derniere["Close"])
    ema_20   = derniere.get("ema_20")
    ema_50   = derniere.get("ema_50")
    ema_200  = derniere.get("ema_200")

    valeurs = [ema_20, ema_50, ema_200]
    if any(v is None or np.isnan(v) for v in valeurs):
        return "Neutre", "Données insuffisantes"

    if prix > ema_20 > ema_50 > ema_200:
        return "Haussière", "Prix > EMA20 > EMA50 > EMA200 (alignement parfait)"
    if prix < ema_20 < ema_50 < ema_200:
        return "Baissière", "Prix < EMA20 < EMA50 < EMA200 (alignement parfait)"
    if prix > ema_50 and ema_50 > ema_200:
        return "Haussière", "Tendance haussière moyen terme (EMA50 > EMA200)"
    if prix < ema_50 and ema_50 < ema_200:
        return "Baissière", "Tendance baissière moyen terme (EMA50 < EMA200)"
    return "Neutre", "EMAs non alignées — marché en consolidation"


def calculer_score(df, tendance: str) -> tuple[int, str, list]:
    """
    Calcule un score de confiance (1-10) basé sur la convergence des signaux.
    Retourne (score, signal, justifications).
    Signal ∈ {ACHAT, VENTE, NEUTRE}.
    """
    derniere   = df.iloc[-1]
    prix       = float(derniere["Close"])
    points     = 0  # négatif = baissier, positif = haussier
    motifs     = []

    # ── Tendance (poids : ±2) ────────────────────────────────────────────────
    if tendance == "Haussière":
        points += 2; motifs.append("Tendance EMA haussière (+2)")
    elif tendance == "Baissière":
        points -= 2; motifs.append("Tendance EMA baissière (-2)")

    # ── RSI (poids : ±1 si extrême) ─────────────────────────────────────────
    rsi = derniere.get("rsi")
    if rsi is not None and not np.isnan(rsi):
        if rsi < 30:
            points += 1; motifs.append(f"RSI survendu ({rsi:.1f}) (+1)")
        elif rsi > 70:
            points -= 1; motifs.append(f"RSI suracheté ({rsi:.1f}) (-1)")

    # ── MACD (poids : ±1) ────────────────────────────────────────────────────
    macd     = derniere.get("macd")
    macd_sig = derniere.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig:
            points += 1; motifs.append("MACD > Signal (haussier) (+1)")
        else:
            points -= 1; motifs.append("MACD < Signal (baissier) (-1)")

    # ── ADX (poids : ±1 si tendance forte) ──────────────────────────────────
    adx = derniere.get("adx")
    if adx is not None and not np.isnan(adx) and adx >= 25:
        if tendance == "Haussière":
            points += 1; motifs.append(f"ADX fort ({adx:.1f}) confirme tendance haussière (+1)")
        elif tendance == "Baissière":
            points -= 1; motifs.append(f"ADX fort ({adx:.1f}) confirme tendance baissière (-1)")

    # ── Divergence RSI (poids : ±2 — très fort signal) ──────────────────────
    divergence = detecter_divergence_rsi(df)
    if divergence == "haussière":
        points += 2; motifs.append("Divergence RSI haussière (+2)")
    elif divergence == "baissière":
        points -= 2; motifs.append("Divergence RSI baissière (-2)")

    # ── Bollinger (poids : ±1 si aux extrêmes) ──────────────────────────────
    bb_upper = derniere.get("bb_upper")
    bb_lower = derniere.get("bb_lower")
    if bb_upper is not None and bb_lower is not None:
        if prix < bb_lower:
            points += 1; motifs.append("Prix sous bande inférieure Bollinger (+1)")
        elif prix > bb_upper:
            points -= 1; motifs.append("Prix au-dessus bande supérieure Bollinger (-1)")

    # ── Patterns (poids : ±2) ───────────────────────────────────────────────
    patterns = detecter_tous_patterns(df)
    for p in patterns:
        if "haussier" in p.lower():
            points += 2; motifs.append(f"{p} (+2)")
        elif "baissier" in p.lower():
            points -= 2; motifs.append(f"{p} (-2)")

    # ── Traduction en score 1-10 ────────────────────────────────────────────
    # points ∈ [-9, +9] environ → score absolu 1-10
    score = min(10, max(1, int(abs(points) + 3)))

    if points >= 3:
        signal = "ACHAT"
    elif points <= -3:
        signal = "VENTE"
    else:
        signal = "NEUTRE"
        score = min(score, 5)  # Jamais un score > 5 si neutre

    return score, signal, motifs


def analyser_actif(ticker: str, timeframe: str = "1d") -> str:
    """
    Analyse technique complète d'un actif sur un timeframe.
    Retourne le rapport formaté (conforme au Skill 1 du CLAUDE.md).
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
