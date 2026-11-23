"""
agents/analysts/market_analyst/score.py — Tendance et score technique 1-10 du Market Analyst.
Sorti de analyst.py (règle des 200 lignes) ; analyst.py le réexporte.
"""

import numpy as np

from utils.indicators import detecter_divergence_rsi
from agents.analysts.market_analyst.patterns import detecter_tous_patterns


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
