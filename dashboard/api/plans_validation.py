"""
dashboard/api/plans_validation.py — Corps de POST et PUT /api/plans : types, bornes, plafond (TODO §7).

- erreur_champs : types et bornes des champs connus (les autres sont ignorés par
  creer_plan et modifier_plan). Montants ≥ 0, allocated_budget_percent entre 0 et 100,
  status dans STATUTS.
- refus_plafond_creation : plafond du mode plan du chat, règle importée telle quelle de
  agents/chat/_plan_budget.py (refus_budget_plan). Il ne concerne qu'un NOUVEAU plan qui
  réservera du budget : actif, et racine ou sous-plan d'un plan inactif (définition de
  _plan_budget). Pour une modification (PUT), la règle n'expose pas de plafond : il
  faudrait retirer la réservation actuelle du plan, calcul interne à plafond_nouveau_plan.
"""

import math

# Aucune liste dans le code : seul « active » est lu (plan_advisor, _plan_budget) ; liste à valider
STATUTS = ("active", "paused", "completed", "archived")
TEXTES = ("name", "plan_type", "objective", "time_horizon", "vision", "risk_tolerance",
          "progress_notes", "investment_reasons", "personal_notes")
MONTANTS = ("allocated_budget", "target_amount", "max_position_size")


def _nombre(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def erreur_champs(data, creation: bool) -> str | None:
    """None si le corps est acceptable, sinon le motif du refus (réponse 400)."""
    if not isinstance(data, dict):
        return "corps JSON (objet) requis"
    if creation and not (data.get("name") and data.get("plan_type")):
        return "name et plan_type requis"
    for k in TEXTES:
        if data.get(k) is not None and not isinstance(data[k], str):
            return f"{k} : texte attendu"
    if "name" in data and not (isinstance(data["name"], str) and data["name"].strip()):
        return "name : texte non vide attendu"
    for k in MONTANTS:
        if data.get(k) is not None and not (_nombre(data[k]) and data[k] >= 0):
            return f"{k} : nombre positif ou nul attendu"
    pct = data.get("allocated_budget_percent")
    if pct is not None and not (_nombre(pct) and 0 <= pct <= 100):
        return "allocated_budget_percent : nombre entre 0 et 100 attendu"
    if data.get("target_return_percent") is not None and not _nombre(data["target_return_percent"]):
        return "target_return_percent : nombre attendu"
    if "status" in data and data["status"] not in STATUTS:
        return f"status : une valeur parmi {', '.join(STATUTS)}"
    regles = data.get("rules")  # creer_plan sérialise un dict ou une liste, modifier_plan non
    if regles is not None and not isinstance(regles, (str, dict, list) if creation else str):
        return "rules : texte attendu" + (" (ou objet JSON)" if creation else "")
    pid = data.get("parent_plan_id")
    if creation and pid is not None and (isinstance(pid, bool) or not isinstance(pid, int)):
        return "parent_plan_id : entier attendu"
    return None


def refus_plafond_creation(data: dict) -> str | None:
    """None si le nouveau plan tient sous le plafond du chat (ou ne réserve rien), sinon le refus."""
    from agents.chat._plan_budget import refus_budget_plan
    from utils.real_portfolio_db import _resoudre_budget, get_budget_capital, lire_plan
    if data.get("status", "active") != "active":
        return None  # inactif : ne réserve rien (actif = status 'active', seul critère lu)
    pid = data.get("parent_plan_id")
    if pid is not None:
        parent = lire_plan(pid)
        if parent is None:
            return f"parent_plan_id {pid} introuvable"
        if parent.get("status") == "active":
            return None  # compris dans le budget de son parent actif, déjà réservé
    montant = _resoudre_budget(dict(data), float(get_budget_capital() or 0)).get("allocated_budget")
    montant = float(montant or 0)  # € ; un % est converti comme pour lire_plans
    return refus_budget_plan(montant) if montant > 0 else None
