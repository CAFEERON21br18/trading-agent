"""
agents/plan_advisor.py — Conseil sur les plans d'investissement (v5.1)
Compare les plans à la réalité et génère des alertes pour MAXIMISER les plans.
Aucune action automatique — l'utilisateur décide.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.real_portfolio_db import (
    lire_plans, positions_du_plan, progression_plan,
    ajouter_alerte_plan, lire_alertes_plans_actives,
)
from utils.data_fetcher import prix_actuel

logger = get_logger(__name__)

# Seuils
DEVIATION_MIN_PCT       = 15  # déviation d'allocation > 15% → alerte
PROFIT_TAKING_MULTIPLE  = 2.0 # x2 → suggérer prise de profit


def _alerte_existe_recemment(plan_id: int, alert_type: str) -> bool:
    """Évite la spamification : ne pas re-créer une alerte du même type non répondue."""
    alertes = lire_alertes_plans_actives()
    return any(a["plan_id"] == plan_id and a["alert_type"] == alert_type for a in alertes)


def _parser_regles(rules_json: str | None) -> dict:
    if not rules_json:
        return {}
    try:
        return json.loads(rules_json)
    except Exception:
        return {}


def verifier_deviation_allocation(plan: dict) -> list[dict]:
    """
    Compare la répartition réelle des positions du plan vs les règles d'allocation.
    Les règles peuvent contenir : {"allocation": {"BTC-USD": 50, "ETH-USD": 30, "autres": 20}}
    """
    alertes = []
    regles = _parser_regles(plan.get("rules"))
    target_alloc = regles.get("allocation")
    if not target_alloc:
        return alertes

    positions = [p for p in positions_du_plan(plan["id"]) if p["status"] == "OPEN"]
    total_invested = sum(p["invested_amount"] for p in positions)
    if total_invested == 0:
        return alertes

    # Calcul de la répartition réelle par ticker
    reelle = {}
    for p in positions:
        reelle[p["asset"]] = reelle.get(p["asset"], 0) + p["invested_amount"]
    reelle_pct = {k: v / total_invested * 100 for k, v in reelle.items()}

    # Comparer chaque entrée des règles
    for ticker, pct_cible in target_alloc.items():
        pct_reel = reelle_pct.get(ticker, 0)
        ecart = pct_reel - pct_cible
        if abs(ecart) > DEVIATION_MIN_PCT:
            sens = "au-dessus" if ecart > 0 else "en-dessous"
            alertes.append({
                "plan_id":    plan["id"],
                "alert_type": "deviation",
                "severity":   "attention",
                "message":    f"Allocation {ticker} : {pct_reel:.0f}% réel vs {pct_cible:.0f}% cible "
                              f"({sens} de {abs(ecart):.0f}%) — rééquilibrer ?",
            })
    return alertes


def verifier_progression_objectif(plan: dict) -> list[dict]:
    """Génère une alerte si l'objectif est proche ou si la progression dévie."""
    alertes = []
    target = plan.get("target_return_percent") or 0
    if target <= 0:
        return alertes

    prog = progression_plan(plan["id"])
    pct_actuel = prog.get("progression_pct", 0)
    avancement = prog.get("avancement_objectif")

    # 1. Objectif atteint à 90%+
    if avancement is not None and avancement >= 90:
        alertes.append({
            "plan_id":    plan["id"],
            "alert_type": "objectif_proche",
            "severity":   "important",
            "message":    f"🎯 Objectif quasi atteint : {pct_actuel:.1f}% vs cible {target:.0f}% "
                          f"({avancement:.0f}% du chemin). Envisage la stratégie de sortie.",
        })
    # 2. Progression bien en avance (> 70% et durée pas écoulée)
    elif avancement is not None and avancement >= 70:
        alertes.append({
            "plan_id":    plan["id"],
            "alert_type": "progression_avance",
            "severity":   "info",
            "message":    f"📊 Plan en avance : {pct_actuel:.1f}% vs cible {target:.0f}%. Bonne dynamique.",
        })
    return alertes


def verifier_prise_profit(plan: dict) -> list[dict]:
    """Détecte les positions qui ont fait ×2 et suggère de prendre une partie."""
    alertes = []
    regles = _parser_regles(plan.get("rules"))
    seuil = regles.get("profit_taking_multiple", PROFIT_TAKING_MULTIPLE)

    positions = [p for p in positions_du_plan(plan["id"]) if p["status"] == "OPEN"]
    for p in positions:
        prix = prix_actuel(p["asset"])
        if prix is None or p["direction"] != "LONG":
            continue
        ratio = prix / p["entry_price"]
        if ratio >= seuil:
            gain_pct = (ratio - 1) * 100
            alertes.append({
                "plan_id":    plan["id"],
                "alert_type": "prise_profit",
                "severity":   "important",
                "message":    f"🎯 {p['asset']} a fait ×{ratio:.2f} (+{gain_pct:.0f}%). "
                              f"Ton plan suggère de prendre une partie des profits. Sécuriser 25-50% ?",
            })
    return alertes


def verifier_taille_position(plan: dict) -> list[dict]:
    """Si une position dépasse max_position_size, prévenir."""
    alertes = []
    max_size = plan.get("max_position_size")
    if not max_size or max_size <= 0:
        return alertes

    positions = [p for p in positions_du_plan(plan["id"]) if p["status"] == "OPEN"]
    for p in positions:
        if p["invested_amount"] > max_size * 1.05:  # 5% tolérance
            alertes.append({
                "plan_id":    plan["id"],
                "alert_type": "taille_position",
                "severity":   "attention",
                "message":    f"⚠️ {p['asset']} ({p['invested_amount']:.0f}€) dépasse la taille max "
                              f"du plan ({max_size:.0f}€). Concentration excessive ?",
            })
    return alertes


def verifier_plan(plan: dict) -> int:
    """Lance toutes les vérifications sur un plan, enregistre les alertes nouvelles."""
    if plan.get("status") != "active":
        return 0
    n = 0
    for check in (verifier_deviation_allocation, verifier_progression_objectif,
                  verifier_prise_profit, verifier_taille_position):
        try:
            for a in check(plan):
                if _alerte_existe_recemment(a["plan_id"], a["alert_type"]):
                    continue
                ajouter_alerte_plan(a["plan_id"], a["alert_type"], a["message"], a["severity"])
                n += 1
                logger.info(f"  💡 Alerte plan #{a['plan_id']} : {a['alert_type']}")
        except Exception as e:
            logger.error(f"verifier_plan ({check.__name__}) : {e}")
    return n


def verifier_tous_les_plans() -> int:
    plans = lire_plans()
    total = 0
    for p in plans:
        total += verifier_plan(p)
    return total
