"""
dashboard/api/routes_plans_suivi.py — Routes des plans d'investissement : lecture, suppression,
progression, alertes (création et modification : plans_routes.py).
Sorti de dashboard/api/routes.py (règle des 200 lignes). Mêmes routes, même blueprint « api » :
routes.py importe ce module en fin de fichier, ce qui enregistre les routes.
"""

from flask import jsonify, request

from dashboard.api.routes import api


# ── v5.1 : Plans d'investissement ─────────────────────────────────────────

@api.route("/plans")
def get_plans():
    from utils.real_portfolio_db import lire_plans, initialiser_real_db
    initialiser_real_db()
    return jsonify(lire_plans())


@api.route("/plans/<int:plan_id>")
def get_plan_detail(plan_id):
    from utils.real_portfolio_db import lire_plan, positions_du_plan
    p = lire_plan(plan_id)
    if not p:
        return jsonify({"error": "Plan introuvable"}), 404
    p["positions"] = positions_du_plan(plan_id)
    return jsonify(p)


# POST et PUT /api/plans : dashboard/api/plans_routes.py (validés, TODO §7)


@api.route("/plans/<int:plan_id>", methods=["DELETE"])
def delete_plan(plan_id):
    from utils.real_portfolio_db import supprimer_plan
    return jsonify({"deleted": supprimer_plan(plan_id)})


@api.route("/plans/<int:plan_id>/progress")
def get_plan_progress(plan_id):
    from utils.real_vue import progression_plan_vue
    return jsonify(progression_plan_vue(plan_id))


@api.route("/plans/alerts")
def get_plan_alerts():
    from utils.real_portfolio_db import lire_alertes_plans_actives
    return jsonify(lire_alertes_plans_actives())


@api.route("/plans/alerts/<int:alert_id>/respond", methods=["POST"])
def post_plan_alert_respond(alert_id):
    from utils.real_portfolio_db import enregistrer_reponse_alerte_plan
    data = request.get_json() or {}
    return jsonify({"recorded": enregistrer_reponse_alerte_plan(alert_id, data.get("decision", ""))})


@api.route("/plans/check-deviations", methods=["POST"])
def post_check_deviations():
    """Force la vérif des déviations plan vs réel + génère alertes."""
    from agents.plan_advisor import verifier_tous_les_plans
    return jsonify({"alertes_creees": verifier_tous_les_plans()})
