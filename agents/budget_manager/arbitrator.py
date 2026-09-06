"""
agents/budget_manager/arbitrator.py — Arbitrage entre demandes de budget concurrentes
Allocation proportionnelle au score (confiance × winrate × urgence), pas division égale.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger(__name__)

# Pondérations urgence (multiplicateur du score)
URGENCE_FACTOR = {"haute": 1.3, "moyenne": 1.0, "basse": 0.7}

# Seuils de viabilité (v5.0 : 15€ min — supporte 20 positions sur 500€ investissables)
MONTANT_MIN_VIABLE = 15.0  # v5: 15€ minimum (était 10€ en v4.1)


def _calculer_score(demande: dict) -> float:
    """Score d'une demande = confiance × (1 + winrate/100) × urgence × boost_qualité (v5.5.2)."""
    conf = float(demande.get("confiance", 0) or 0)
    winrate = float(demande.get("winrate_historique", 50.0))  # 50% par défaut si inconnu
    urgence = demande.get("urgence", "moyenne").lower()
    boost = float(demande.get("budget_boost", 1.0) or 1.0)   # v5.5.2 : bonus/malus selon grade A/B/C/D
    return conf * (1 + winrate / 100) * URGENCE_FACTOR.get(urgence, 1.0) * boost


def arbitrer(demandes: list[dict], cash_disponible: float, mode_params: dict,
             max_par_trade_pct: float | None = None) -> dict:
    """
    Reçoit une liste de demandes + cash dispo + paramètres du mode.
    Retourne :
      {
        "allocations": list[dict] — décisions par demande (financée ou refusée),
        "total_alloue": float,
        "cash_restant": float,
        "en_attente":   list[dict] — demandes en file d'attente,
      }
    """
    if not demandes or cash_disponible <= 0:
        return {"allocations": [], "total_alloue": 0.0, "cash_restant": cash_disponible, "en_attente": []}

    # ── 1. Filtrer les demandes qui passent le seuil de confiance du mode ─────
    conf_min = mode_params["confiance_min"]
    valides, rejetees_conf = [], []
    for d in demandes:
        if float(d.get("confiance", 0) or 0) < conf_min:
            d["raison_refus"] = f"Confiance {d['confiance']}/10 < seuil mode ({conf_min}/10)"
            rejetees_conf.append(d)
        else:
            valides.append(d)

    # ── 2. Calculer les scores et trier par score décroissant ────────────────
    scored = [(d, _calculer_score(d)) for d in valides]
    scored.sort(key=lambda x: x[1], reverse=True)

    # ── 3. Allocation proportionnelle ────────────────────────────────────────
    total_score = sum(s for _, s in scored) or 1.0
    max_par_trade = (max_par_trade_pct or mode_params["max_conviction_par_trade"]) / 100 * cash_disponible
    taille_factor = mode_params["taille_factor"]

    allocations = []
    cash_alloue = 0.0
    en_attente  = []

    for d, score in scored:
        cash_restant = cash_disponible - cash_alloue
        if cash_restant <= MONTANT_MIN_VIABLE:
            d["raison_refus"] = "Plus assez de cash disponible"
            en_attente.append(d)
            continue

        # Part proportionnelle, capée par max_par_trade et cash restant
        budget_brut = (score / total_score) * cash_disponible * taille_factor
        budget = min(budget_brut, max_par_trade, cash_restant, d.get("budget_souhaité", budget_brut))

        if budget < MONTANT_MIN_VIABLE:
            d["raison_refus"] = f"Budget alloué {budget:.0f}€ < minimum viable {MONTANT_MIN_VIABLE:.0f}€"
            en_attente.append(d)
            continue

        allocations.append({
            "demande":          d,
            "budget_alloue":    round(budget, 2),
            "budget_demande":   d.get("budget_souhaité"),
            "score":            round(score, 2),
            "raison_allocation": (f"Score {score:.1f} sur total {total_score:.1f} "
                                  f"({budget / cash_disponible * 100:.1f}% du cash)"),
        })
        cash_alloue += budget

    # Ajouter les rejetées par confiance dans en_attente
    en_attente.extend(rejetees_conf)

    return {
        "allocations":  allocations,
        "total_alloue": round(cash_alloue, 2),
        "cash_restant": round(cash_disponible - cash_alloue, 2),
        "en_attente":   en_attente,
    }
