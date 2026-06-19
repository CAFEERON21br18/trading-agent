"""
agents/paper_trader/rotation.py — Rotation de portefeuille (v5.0)
Si les 20 slots sont pleins ET qu'une meilleure opportunité arrive,
identifie la position la plus faible pour faire place à la nouvelle.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import lire_positions_ouvertes

logger = get_logger(__name__)


def _score_position(p: dict) -> float:
    """
    Score d'une position (plus c'est bas, plus c'est candidat à fermeture).
    Combine confiance d'entrée + P&L latent (si dispo) + statut.
    """
    confiance = float(p.get("confidence") or 0)
    pnl_pct   = float(p.get("unrealized_pnl_pct") or 0)
    # Plus la confiance était haute ET plus on est en profit → score élevé (à garder)
    # Plus on est en perte → score faible (candidat à fermer)
    return confiance * 0.6 + pnl_pct * 0.4


def position_la_plus_faible() -> dict | None:
    """Retourne la position ouverte avec le plus mauvais score, ou None si <max."""
    positions = lire_positions_ouvertes()
    if len(positions) < config.MAX_POSITIONS_SIMULTANEES:
        return None
    if not positions:
        return None
    return min(positions, key=_score_position)


def suggerer_rotation(nouvelle_confiance: int, nouvelle_score_composite: float) -> dict | None:
    """
    Si on est plein ET la nouvelle opportunité est meilleure que la plus faible,
    retourne la position à fermer avec la raison. Sinon None.

    Critère "meilleure" : nouvelle_confiance >= confidence_min_existante + 2
    OU nouvelle_score_composite > score_le_plus_faible + 1.5
    """
    faible = position_la_plus_faible()
    if faible is None:
        return None

    score_faible = _score_position(faible)
    gain_minimum = 2  # 2 points de confiance de mieux pour justifier la rotation

    if nouvelle_confiance >= (faible.get("confidence") or 0) + gain_minimum:
        return {
            "position_a_fermer": faible,
            "raison": f"Rotation : meilleure opportunité (conf {nouvelle_confiance}/10 "
                      f"vs {faible.get('confidence', '?')}/10 actuelle)",
            "score_actuel":     score_faible,
        }

    return None
