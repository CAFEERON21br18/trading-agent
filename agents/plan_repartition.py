"""
agents/plan_repartition.py — Contrôle de répartition d'un plan d'après sa structure réelle (TODO §31).

Les plans réels n'ont pas de clé « allocation » (répartition par ticker) :
- rules["repartition"] (plan Global) : {plan_type d'un sous-plan direct: % cible}. Contrôlé : part de
  l'investi ouvert de chaque sous-plan (lui et ses descendants) dans l'investi total des sous-plans
  cités, comparée à la cible ;
- rules["sous_repartition"] (sous-plans) : catégories qui ne désignent ni un sous-plan ni, sans
  ambiguïté, une liste d'actifs. NON contrôlé (voir TODO §31).
Aucun contrôle, avec une ligne de log, si la structure est ambiguë : une clé qui ne désigne pas
exactement un sous-plan direct, une cible qui ne fait pas 100 %, des positions ouvertes sur le plan
lui-même ou dans un sous-plan non cité, ou un taux de change introuvable.
Une seule alerte « deviation » par plan, listant les écarts de plus de DEVIATION_MIN_PCT points.
"""

import json

from utils.logger import get_logger
from utils.real_conversion import investi_en_eur
from utils.real_devise import devise_commune
from utils.real_portfolio_db import positions_du_plan

logger = get_logger(__name__)

DEVIATION_MIN_PCT = 15  # écart de répartition > 15 points → alerte


def _regles(plan: dict) -> dict:
    regles = plan.get("rules")
    if isinstance(regles, dict):
        return regles
    try:
        return json.loads(regles) if regles else {}
    except Exception:
        return {}


def _sous_arbre(plan_id: int, plans: list[dict]) -> list[int]:
    ids, a_voir = [], [plan_id]
    while a_voir:
        i = a_voir.pop(0)
        if i not in ids:
            ids.append(i)
            a_voir += [p["id"] for p in plans if p.get("parent_plan_id") == i]
    return ids


def _ouvertes(ids: list[int]) -> list[dict]:
    return [p for i in ids for p in positions_du_plan(i) if p["status"] == "OPEN"]


def _ambigu(plan: dict, raison: str) -> list:
    logger.info(f"Plan #{plan['id']} : répartition non contrôlée ({raison})")
    return []


def verifier_repartition(plan: dict, plans: list[dict]) -> list[dict]:
    """Alertes de répartition du plan (au plus une), d'après rules["repartition"]."""
    cible = _regles(plan).get("repartition")
    if not isinstance(cible, dict) or not cible:
        return []
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in cible.values()):
        return _ambigu(plan, "cible non numérique")
    if abs(sum(cible.values()) - 100) > 0.5:
        return _ambigu(plan, f"cible de {sum(cible.values()):g} % au lieu de 100 %")
    enfants = [p for p in plans if p.get("parent_plan_id") == plan["id"]]
    par_cle = {k: [e for e in enfants if e.get("plan_type") == k] for k in cible}
    if any(len(v) != 1 for v in par_cle.values()):
        return _ambigu(plan, "une clé ne désigne pas exactement un sous-plan direct")
    if _ouvertes([plan["id"]]):
        return _ambigu(plan, "positions ouvertes rattachées au plan lui-même")
    cites = {v[0]["id"] for v in par_cle.values()}
    if any(_ouvertes(_sous_arbre(e["id"], plans)) for e in enfants if e["id"] not in cites):
        return _ambigu(plan, "positions ouvertes dans un sous-plan absent de la répartition")
    positions = {k: _ouvertes(_sous_arbre(v[0]["id"], plans)) for k, v in par_cle.items()}
    toutes = [p for v in positions.values() for p in v]
    if not toutes:
        return []
    if devise_commune(toutes):  # même devise partout : parts sans conversion
        investi = {k: sum(float(p["invested_amount"]) for p in v) for k, v in positions.items()}
    else:
        investi = {k: investi_en_eur(v)[0] if v else 0.0 for k, v in positions.items()}
        if any(x is None for x in investi.values()):
            return _ambigu(plan, "taux de change introuvable")
    total = sum(investi.values())
    if total <= 0:
        return []
    ecarts = []
    for k, pct_cible in cible.items():
        reel = investi[k] / total * 100
        if abs(reel - pct_cible) > DEVIATION_MIN_PCT:
            ecarts.append(f"{k} {reel:.0f} % réel vs {pct_cible:g} % cible ({reel - pct_cible:+.0f} points)")
    if not ecarts:
        return []
    return [{"plan_id": plan["id"], "alert_type": "deviation", "severity": "attention",
             "message": f"Répartition hors cible (écart de plus de {DEVIATION_MIN_PCT} points) : "
                        + " ; ".join(ecarts) + ". Rééquilibrer ?"}]
