"""
dashboard/api/plans_routes.py — POST et PUT /api/plans, validés (TODO §7).

Sortis de routes.py (plus de 200 lignes, règle 5) : mêmes URL et mêmes réponses qu'avant, plus
un 400 {"error": motif} quand la demande est refusée (dashboard/api/plans_validation.py) :
- POST : types et bornes, puis plafond du mode plan du chat ;
- PUT : types et bornes seulement (pas de plafond pour une modification, voir plans_validation).
GET et DELETE /api/plans restent dans routes.py.
"""

from flask import Blueprint, jsonify, request

from dashboard.api.plans_validation import erreur_champs, refus_plafond_creation

plans_api = Blueprint("plans_api", __name__, url_prefix="/api")


@plans_api.route("/plans", methods=["POST"])
def post_plan():
    from utils.real_portfolio_db import creer_plan
    data = request.get_json(silent=True)
    refus = erreur_champs(data, creation=True) or refus_plafond_creation(data)
    if refus:
        return jsonify({"error": refus}), 400
    return jsonify({"id": creer_plan(data), "saved": True})


@plans_api.route("/plans/<int:plan_id>", methods=["PUT"])
def put_plan(plan_id):
    from utils.real_portfolio_db import modifier_plan
    data = request.get_json(silent=True)
    refus = erreur_champs(data, creation=False)
    if refus:
        return jsonify({"error": refus}), 400
    return jsonify({"updated": modifier_plan(plan_id, data)})
