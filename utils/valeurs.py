"""
utils/valeurs.py — Valeurs numériques sûres (Phase 4, prix NULL de la table prices).

Une valeur manquante (None, NaN, infini, texte illisible) reste inconnue :
None, jamais 0. pandas renvoie NaN pour une valeur absente, et `NaN or 0`
vaut NaN : l'ancien motif `float(v or 0)` laissait donc passer les NaN.
"""

import math

OHLC = ("Open", "High", "Low", "Close")


def nombre_ou_none(v) -> float | None:
    """float fini, ou None si la valeur est inconnue."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def ohlc_ou_none(row) -> tuple | None:
    """(open, high, low, close) d'une ligne pandas, ou None s'il en manque un."""
    valeurs = tuple(nombre_ou_none(row.get(c)) for c in OHLC)
    return None if None in valeurs else valeurs
