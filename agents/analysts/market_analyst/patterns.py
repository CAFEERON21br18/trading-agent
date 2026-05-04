"""
agents/market_analyst/patterns.py — Détection de patterns chartistes
Patterns détectés : double top, double bottom, head & shoulders, triangles, breakouts
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger

logger = get_logger(__name__)


def detecter_pivots(df: pd.DataFrame, fenetre: int = 5) -> tuple[list, list]:
    """
    Identifie les pivots hauts (sommets) et bas (creux) locaux.
    Un pivot haut/bas est un point dont le haut/bas est plus grand/petit que les N bougies adjacentes.
    Retourne (pivots_hauts, pivots_bas) sous forme de listes de (index, prix).
    """
    pivots_hauts = []
    pivots_bas   = []

    for i in range(fenetre, len(df) - fenetre):
        haut = float(df["High"].iloc[i])
        bas  = float(df["Low"].iloc[i])

        # Pivot haut : le plus haut sur la fenêtre autour
        voisins_hauts = df["High"].iloc[i-fenetre:i+fenetre+1]
        if haut == voisins_hauts.max():
            pivots_hauts.append((i, haut))

        # Pivot bas : le plus bas sur la fenêtre autour
        voisins_bas = df["Low"].iloc[i-fenetre:i+fenetre+1]
        if bas == voisins_bas.min():
            pivots_bas.append((i, bas))

    return pivots_hauts, pivots_bas


def detecter_double_top(df: pd.DataFrame, tolerance_pct: float = 2.0) -> bool:
    """
    Détecte un double top (deux sommets à même hauteur).
    Pattern baissier : tolerance_pct = écart max entre les deux sommets (%)
    """
    try:
        pivots_hauts, _ = detecter_pivots(df.tail(60))
        if len(pivots_hauts) < 2:
            return False

        # Comparer les deux derniers pivots hauts
        _, prix_1 = pivots_hauts[-2]
        _, prix_2 = pivots_hauts[-1]
        ecart_pct = abs(prix_1 - prix_2) / prix_1 * 100
        return ecart_pct <= tolerance_pct
    except Exception as e:
        logger.error(f"Erreur détection double top : {e}")
        return False


def detecter_double_bottom(df: pd.DataFrame, tolerance_pct: float = 2.0) -> bool:
    """
    Détecte un double bottom (deux creux à même hauteur).
    Pattern haussier : tolerance_pct = écart max entre les deux creux (%)
    """
    try:
        _, pivots_bas = detecter_pivots(df.tail(60))
        if len(pivots_bas) < 2:
            return False

        _, prix_1 = pivots_bas[-2]
        _, prix_2 = pivots_bas[-1]
        ecart_pct = abs(prix_1 - prix_2) / prix_1 * 100
        return ecart_pct <= tolerance_pct
    except Exception as e:
        logger.error(f"Erreur détection double bottom : {e}")
        return False


def detecter_breakout(df: pd.DataFrame, periode: int = 20) -> str:
    """
    Détecte un breakout de range (cassure du plus haut/bas des N dernières bougies).
    Retourne : "haussier", "baissier", ou "aucun"
    """
    try:
        if len(df) < periode + 1:
            return "aucun"

        fenetre = df.tail(periode + 1)
        range_haut = float(fenetre["High"].iloc[:-1].max())
        range_bas  = float(fenetre["Low"].iloc[:-1].min())
        close_actuel = float(df["Close"].iloc[-1])

        # Confirmation volume : volume actuel > moyenne sur la période
        vol_actuel = float(df["Volume"].iloc[-1])
        vol_moyen  = float(df["Volume"].tail(periode).mean())
        volume_confirme = vol_actuel > vol_moyen

        if close_actuel > range_haut and volume_confirme:
            return "haussier"
        if close_actuel < range_bas and volume_confirme:
            return "baissier"
        return "aucun"
    except Exception as e:
        logger.error(f"Erreur détection breakout : {e}")
        return "aucun"


def detecter_tous_patterns(df: pd.DataFrame) -> list[str]:
    """Retourne la liste des patterns identifiés sur le DataFrame."""
    patterns = []

    if detecter_double_top(df):
        patterns.append("Double top (baissier)")
    if detecter_double_bottom(df):
        patterns.append("Double bottom (haussier)")

    breakout = detecter_breakout(df)
    if breakout == "haussier":
        patterns.append("Breakout haussier avec volume")
    elif breakout == "baissier":
        patterns.append("Breakout baissier avec volume")

    return patterns


def calculer_fibonacci(df: pd.DataFrame, lookback: int = 100) -> dict:
    """
    Calcule les niveaux de retracement Fibonacci sur les `lookback` dernières bougies.
    Détecte automatiquement la tendance dominante : si plus haut récent > plus bas récent
    en termes de timing → tendance haussière → retrace depuis le high.

    Retourne :
      {
        "tendance":   "haussière" | "baissière",
        "high":       prix le plus haut sur la fenêtre,
        "low":        prix le plus bas sur la fenêtre,
        "niveaux":    {"0%": prix, "23.6%": prix, "38.2%": prix,
                       "50%": prix, "61.8%": prix, "78.6%": prix, "100%": prix},
        "niveau_proche": label du niveau le plus proche du prix actuel,
      }
    """
    if df.empty or len(df) < 20:
        return {}

    sous_df = df.tail(lookback) if len(df) > lookback else df
    high     = float(sous_df["High"].max())
    low      = float(sous_df["Low"].min())
    diff     = high - low
    if diff <= 0:
        return {}

    idx_high = sous_df["High"].idxmax()
    idx_low  = sous_df["Low"].idxmin()
    haussiere = idx_low < idx_high  # le low vient avant le high → tendance haussière

    # Pourcentages standards
    fib_pcts = {"0%": 0.0, "23.6%": 0.236, "38.2%": 0.382,
                "50%": 0.5, "61.8%": 0.618, "78.6%": 0.786, "100%": 1.0}

    niveaux = {}
    for label, pct in fib_pcts.items():
        if haussiere:
            # Retracement depuis le high vers le low
            niveaux[label] = high - diff * pct
        else:
            # Retracement depuis le low vers le high
            niveaux[label] = low + diff * pct

    # Niveau le plus proche du prix actuel
    prix_actuel = float(df["Close"].iloc[-1])
    niveau_proche = min(niveaux.items(), key=lambda kv: abs(kv[1] - prix_actuel))

    return {
        "tendance":      "haussière" if haussiere else "baissière",
        "high":          high,
        "low":           low,
        "niveaux":       niveaux,
        "niveau_proche": {"label": niveau_proche[0], "prix": niveau_proche[1]},
        "prix_actuel":   prix_actuel,
    }
