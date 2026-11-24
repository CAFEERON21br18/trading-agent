"""
utils/indicators_lecture.py — Lecture des indicateurs : divergence RSI, niveaux clés,
interprétation du RSI et de l'ADX.
Sorti de utils/indicators.py (règle des 200 lignes) ; indicators.py le réexporte.
"""

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger("utils.indicators")  # même nom de journal qu'avant le découpage


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
