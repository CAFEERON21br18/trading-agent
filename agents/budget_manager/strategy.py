"""
agents/budget_manager/strategy.py — Détection du mode actuel + paramètres
4 modes : NORMAL, DEFENSIF, AGRESSIF, CONVICTION (manuel).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import lire_positions_recentes_fermees

logger = get_logger(__name__)

# Seuils de bascule entre modes
PERTES_DEFENSIF       = 3       # 3 pertes consécutives → défensif
WINS_AGRESSIF         = 5       # 5 wins consécutifs → agressif
DRAWDOWN_DEFENSIF_PCT = 8.0     # drawdown total > 8% → défensif
GAIN_AGRESSIF_PCT     = 10.0    # gain portefeuille > 10% → agressif

# Paramètres par mode (v4.1 : seuils abaissés pour favoriser l'apprentissage)
PARAMETRES = {
    "NORMAL": {
        "capital_investissable_pct": 50.0,
        "confiance_min":              4,    # v4.1 : 4 (avant 7) — accepte les trades d'apprentissage
        "taille_factor":              1.0,
        "max_conviction_par_trade":   10.0, # v5 : 10% max/trade (avant 25%) — supporte 20 positions
    },
    "DEFENSIF": {
        "capital_investissable_pct": 30.0,
        "confiance_min":              7,    # v4.1 : 7 (avant 8)
        "taille_factor":              0.5,
        "max_conviction_par_trade":   20.0,
    },
    "AGRESSIF": {
        "capital_investissable_pct": 50.0,
        "confiance_min":              3,    # v4.1 : 3 (avant 5) — très permissif en agressif
        "taille_factor":              1.3,
        "max_conviction_par_trade":   35.0,
    },
    "CONVICTION": {
        "capital_investissable_pct": 50.0,
        "confiance_min":              8,    # v4.1 : 8 (avant 9)
        "taille_factor":              1.0,
        "max_conviction_par_trade":   40.0,
    },
}


def _wins_pertes_consecutives(positions: list[dict]) -> tuple[int, int]:
    """Compte les wins/pertes consécutives à partir des positions les plus récentes."""
    wins, pertes = 0, 0
    for p in positions:
        pnl = p.get("pnl_euros") or 0
        if pnl > 0:
            if pertes > 0:
                break
            wins += 1
        elif pnl < 0:
            if wins > 0:
                break
            pertes += 1
        else:
            break
    return wins, pertes


def _drawdown_recent_pct(positions: list[dict]) -> float:
    """Calcule le drawdown total depuis les N dernières positions fermées."""
    if not positions:
        return 0.0
    pnl_total = sum((p.get("pnl_euros") or 0) for p in positions)
    if pnl_total >= 0:
        return 0.0
    return abs(pnl_total) / config.CAPITAL * 100


def detecter_mode(conviction_force: bool = False) -> str:
    """Détecte le mode actuel du Budget Manager (NORMAL / DEFENSIF / AGRESSIF / CONVICTION)."""
    if conviction_force:
        return "CONVICTION"

    fermees = lire_positions_recentes_fermees(limite=20)
    wins, pertes = _wins_pertes_consecutives(fermees)
    drawdown = _drawdown_recent_pct(fermees[:10])  # drawdown récent (10 trades)

    if pertes >= PERTES_DEFENSIF or drawdown > DRAWDOWN_DEFENSIF_PCT:
        return "DEFENSIF"
    if wins >= WINS_AGRESSIF:
        # Vérifier le gain global du portefeuille
        gain_global_pct = sum((p.get("pnl_euros") or 0) for p in fermees[:20]) / config.CAPITAL * 100
        if gain_global_pct >= GAIN_AGRESSIF_PCT:
            return "AGRESSIF"
    return "NORMAL"


def parametres_mode(mode: str) -> dict:
    """Retourne les paramètres associés au mode."""
    return PARAMETRES.get(mode, PARAMETRES["NORMAL"]).copy()


def capital_investissable(mode: str | None = None) -> float:
    """Capital investissable en € selon le mode."""
    mode = mode or detecter_mode()
    pct = parametres_mode(mode)["capital_investissable_pct"]
    return config.CAPITAL * (pct / 100)


def diagnostic() -> dict:
    """Snapshot pour le tableau de bord."""
    fermees = lire_positions_recentes_fermees(limite=20)
    wins, pertes = _wins_pertes_consecutives(fermees)
    return {
        "mode":               detecter_mode(),
        "wins_consecutifs":   wins,
        "pertes_consecutives": pertes,
        "drawdown_pct":       round(_drawdown_recent_pct(fermees[:10]), 2),
        "trades_fermes_20":   len(fermees),
    }
