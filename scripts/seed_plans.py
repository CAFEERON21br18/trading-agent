"""
scripts/seed_plans.py — Insère le plan d'investissement complet de l'utilisateur
(plan global + 3 sous-plans : long terme, moyen terme, court terme).

IDÉMPOTENT : si "Plan Global" existe déjà, ne fait rien.
Utilisation : python scripts/seed_plans.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.real_portfolio_db import (
    initialiser_real_db, lire_plans, creer_plan,
    get_budget_capital, set_budget_capital, _resoudre_budget,
)
from utils.logger import get_logger

logger = get_logger("seed_plans")


PLANS_DEFINITION = [
    {
        "plan_type": "global",
        "name": "Plan Global",
        "parent_plan": None,
        "objective": "Faire travailler l'argent qui dort, croissance régulière à risque maîtrisé",
        "time_horizon": "continu, révision tous les 3 mois",
        "vision": ("Investir dans le futur (IA, énergie, semi-conducteurs, infra) long terme, "
                   "capter des opportunités fort potentiel moyen terme, profiter de la volatilité "
                   "bien analysée court terme"),
        "risk_tolerance": "moyenne",
        "allocated_budget_percent": 100,
        "rules": {
            "repartition": {"long_terme": 50, "moyen_terme": 30, "court_terme": 20},
            "revision":    "tous les 3 mois",
            "objectifs":   "souples",
        },
        "status": "active",
    },
    {
        "plan_type": "long_terme",
        "name": "Long Terme",
        "parent_plan": "Plan Global",
        "objective": "Socle solide investi dans le futur, faible rotation, on garde et renforce",
        "time_horizon": "2-5 ans",
        "vision": "IA, datacenters, semi-conducteurs, énergie nucléaire, Bitcoin comme réserve",
        "risk_tolerance": "faible-moyenne",
        "allocated_budget_percent": 50,
        "rules": {
            "sous_repartition": {"crypto_socle": 25, "actions_futur": 55, "indices": 20},
            "crypto":           ["BTC-USD"],
            "actions":          ["VRT", "AMAT", "AMD", "MU", "LITE", "VST", "CEG"],
            "indices":          ["QQQ", "VOO"],
            "strategie":        "DCA, renforcer sur corrections, réviser thèse tous les 3 mois",
            "sortie":           "seulement si la thèse de fond est cassée",
        },
        "status": "active",
    },
    {
        "plan_type": "moyen_terme",
        "name": "Moyen Terme",
        "parent_plan": "Plan Global",
        "objective": "Capter des opportunités fort potentiel (>100%) sur semaines/mois + petits gains réguliers",
        "time_horizon": "semaines à quelques mois",
        "vision": "Alts crypto établies, actions à momentum, trades quotidiens petits gains",
        "risk_tolerance": "moyenne",
        "allocated_budget_percent": 30,
        "rules": {
            "sous_repartition": {"crypto_moyen": 35, "actions": 40, "trades_quotidiens_paris": 25},
            "crypto":           ["CRO-USD", "HBAR-USD"],
            "prise_profit":     "sécuriser 25-30% sur un x2",
            "diversification":  "ne pas tout miser sur un seul pari",
            "stop_loss":        "obligatoire sur positions actives",
        },
        "status": "active",
    },
    {
        "plan_type": "court_terme",
        "name": "Court Terme",
        "parent_plan": "Plan Global",
        "objective": "Profiter de la volatilité et des facteurs spéculatifs bien analysés, gains rapides",
        "time_horizon": "heures à jours",
        "vision": "Trading actif sur actifs volatils avec gestion du risque stricte",
        "risk_tolerance": "élevée",
        "allocated_budget_percent": 20,
        "rules": {
            "composition": ["CFD", "crypto_volatile", "speculatif_analyse"],
            "stop_loss":   "OBLIGATOIRE et serré sur chaque trade",
            "condition":   "jamais de trade sans analyse approfondie",
            "cfd_warning": "surveiller l'effet de levier",
            "plafond":     "ne jamais dépasser 20% du capital total",
            "discipline":  "couper les pertes vite, laisser courir les gains",
        },
        "status": "active",
    },
]


def main() -> int:
    initialiser_real_db()

    # Si le capital n'est pas défini, mettre 1000€ par défaut (à modifier via la web app)
    capital = get_budget_capital()
    if capital <= 0:
        logger.warning("Capital total non défini → fixe à 1000€ par défaut. "
                       "Modifie via la page Réel (✎ Modifier total).")
        set_budget_capital(1000.0)
        capital = 1000.0

    # Vérifier idempotence
    existants = lire_plans()
    noms_existants = {p["name"] for p in existants}
    if "Plan Global" in noms_existants:
        logger.info("Plan Global déjà présent — seed skipé.")
        _afficher_recap()
        return 0

    # Insérer les plans dans l'ordre (global d'abord pour avoir son id)
    parent_id_map: dict[str, int] = {}
    for p_def in PLANS_DEFINITION:
        payload = {k: v for k, v in p_def.items() if k != "parent_plan"}
        if p_def.get("parent_plan"):
            payload["parent_plan_id"] = parent_id_map.get(p_def["parent_plan"])
        pid = creer_plan(payload)
        parent_id_map[p_def["name"]] = pid
        logger.info(f"  ✓ Créé plan #{pid} : {p_def['name']}")

    _afficher_recap()
    return 0


def _afficher_recap() -> None:
    capital = get_budget_capital()
    plans = lire_plans()
    print()
    print(f"━━━ Récapitulatif (capital total : {capital:.0f}€) ━━━")
    print(f"{'Nom':<14} {'Type':<14} {'Parent':<14} {'%':>5}  {'€':>10}  Objectif")
    print("─" * 100)
    for p in plans:
        parent = ""
        if p.get("parent_plan_id"):
            par = next((x for x in plans if x["id"] == p["parent_plan_id"]), None)
            parent = par["name"] if par else "?"
        pct = p.get("allocated_budget_percent") or 0
        eur = p.get("allocated_budget") or 0
        obj = (p.get("objective") or "")[:50]
        print(f"{p['name']:<14} {p['plan_type']:<14} {parent:<14} {pct:>4.0f}%  {eur:>8.0f}€  {obj}")


if __name__ == "__main__":
    sys.exit(main())
