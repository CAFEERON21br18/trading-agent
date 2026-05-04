"""
agents/risk_manager/position_sizer.py — Calcul de la taille de position et des niveaux
Formules basées sur le risque fixe par trade (% du capital) et l'ATR pour les stops.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger

logger = get_logger(__name__)


def calculer_stop_loss(prix_entree: float, direction: str, atr: float,
                       support: float | None = None, resistance: float | None = None,
                       multiplicateur_atr: float = 1.5) -> float:
    """
    Calcule le stop-loss en utilisant la méthode la plus conservatrice :
      - LONG : max entre (entrée - ATR × 1.5) et support (le plus proche au-dessus)
      - SHORT : min entre (entrée + ATR × 1.5) et résistance (la plus proche en dessous)
    """
    if direction == "LONG":
        stop_atr = prix_entree - (atr * multiplicateur_atr)
        # Si un support est valide (sous l'entrée), on prend le max (le plus proche de l'entrée)
        if support is not None and support < prix_entree:
            return max(stop_atr, support * 0.995)  # Petit buffer sous le support
        return stop_atr

    if direction == "SHORT":
        stop_atr = prix_entree + (atr * multiplicateur_atr)
        if resistance is not None and resistance > prix_entree:
            return min(stop_atr, resistance * 1.005)
        return stop_atr

    return prix_entree


def calculer_targets(prix_entree: float, stop_loss: float,
                     direction: str) -> tuple[float, float]:
    """
    Calcule Target 1 (R:R 1:2) et Target 2 (R:R 1:3) à partir du stop-loss.
    """
    distance_stop = abs(prix_entree - stop_loss)

    if direction == "LONG":
        target_1 = prix_entree + (distance_stop * 2)
        target_2 = prix_entree + (distance_stop * 3)
    else:
        target_1 = prix_entree - (distance_stop * 2)
        target_2 = prix_entree - (distance_stop * 3)

    return target_1, target_2


def calculer_taille_position(capital_total: float, risque_pct: float,
                             prix_entree: float, stop_loss: float,
                             cash_disponible: float | None = None,
                             nb_positions_visees: int = 1,
                             max_invested_pct: float = 50.0,
                             budget_alloue: float | None = None) -> dict:
    """
    Calcule la taille de position avec budget partagé + cash réserve intouchable.

    Règle : la taille finale = MIN(taille_par_risque, taille_par_budget).
    Le risque par trade reste plafonné à risque_pct du capital_total (ex: 2%).
    Le budget par position respecte la réserve cash de (100 - max_invested_pct)%.

    Args :
        capital_total       : capital de référence (ex: 1000€)
        risque_pct          : % de risque max par trade (ex: 2 pour 2%)
        prix_entree         : prix d'entrée envisagé
        stop_loss           : prix du stop-loss
        cash_disponible     : cash actuellement non investi (None → capital_investissable)
        nb_positions_visees : combien de positions à ouvrir simultanément
        max_invested_pct    : % max du capital investi simultanément (ex: 50)
        budget_alloue       : montant € imposé par le Budget Manager (prime sur le calcul auto)

    Retourne un dict détaillé avec toutes les valeurs intermédiaires.
    """
    capital_investissable = capital_total * (max_invested_pct / 100)
    if cash_disponible is None:
        cash_disponible = capital_investissable

    # Si le BM a déjà alloué un budget, il prime. Sinon, calcul auto par division.
    budget_total = min(cash_disponible, capital_investissable)
    if budget_alloue is not None and budget_alloue > 0:
        budget_par_pos = min(budget_alloue, budget_total)
    else:
        budget_par_pos = budget_total / max(1, nb_positions_visees)

    distance_stop = abs(prix_entree - stop_loss)
    if distance_stop <= 0:
        return {
            "erreur":                    "Distance au stop nulle ou invalide",
            "capital_total":             capital_total,
            "capital_investissable":     capital_investissable,
            "budget_par_position":       budget_par_pos,
            "distance_stop":             0,
            "taille_unites":             0,
            "montant_investi":           0,
            "montant_risque_theorique":  0,
            "montant_risque_reel":       0,
            "limite_active":             "ERREUR",
        }

    risque_max_eur     = capital_total * (risque_pct / 100)
    taille_par_risque  = risque_max_eur / distance_stop
    taille_par_budget  = budget_par_pos / prix_entree
    taille_unites      = min(taille_par_risque, taille_par_budget)
    limite_active      = "RISQUE" if taille_par_risque <= taille_par_budget else "BUDGET"
    montant_investi    = taille_unites * prix_entree
    risque_reel        = taille_unites * distance_stop

    if montant_investi > budget_par_pos + 0.01:  # tolérance flottants
        logger.error(f"BUG: montant {montant_investi:.2f}€ > budget {budget_par_pos:.2f}€")

    return {
        "capital_total":             capital_total,
        "capital_investissable":     capital_investissable,
        "cash_disponible":           cash_disponible,
        "budget_par_position":       budget_par_pos,
        "nb_positions_visees":       nb_positions_visees,
        "distance_stop":             distance_stop,
        "taille_unites":             taille_unites,
        "montant_investi":           montant_investi,
        "montant_risque_theorique":  risque_max_eur,
        "montant_risque_reel":       risque_reel,
        "limite_active":             limite_active,  # quelle contrainte a primé
        "budget_restant_apres":      budget_total - montant_investi,
    }


def calculer_rr(prix_entree: float, stop_loss: float, target: float, direction: str) -> float:
    """Calcule le ratio risque/récompense pour un target donné."""
    risque = abs(prix_entree - stop_loss)
    if risque == 0:
        return 0
    if direction == "LONG":
        recompense = target - prix_entree
    else:
        recompense = prix_entree - target
    return recompense / risque if risque > 0 else 0
