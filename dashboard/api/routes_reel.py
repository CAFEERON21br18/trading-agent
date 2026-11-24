"""
dashboard/api/routes_reel.py — Routes du portefeuille réel : positions, conseils, budget.
Sorti de dashboard/api/routes.py (règle des 200 lignes). Mêmes routes, même blueprint « api » :
routes.py importe ce module en fin de fichier, ce qui enregistre les routes.
"""

from flask import jsonify, request

from dashboard.api.routes import api


# ── v5.0 — Portefeuille RÉEL ─────────────────────────────────────────────

@api.route("/real/portfolio")
def get_real_portfolio():
    """Résumé du portefeuille réel, avec la devise des positions (D1)."""
    from utils.real_vue import resume_portefeuille_vue
    return jsonify(resume_portefeuille_vue())


@api.route("/real/investments")
def get_real_investments():
    """Liste filtrable des investissements réels."""
    from utils.real_portfolio_db import lire_investissements
    from agents.real_advisor import _enrichir
    status = request.args.get("status")
    holding = request.args.get("holding")
    instrument = request.args.get("instrument")
    invs = lire_investissements(filtre_status=status, filtre_holding=holding,
                                 filtre_instrument=instrument)
    # On enrichit avec prix actuel + P&L latent (timeout court via data_fetcher cache)
    return jsonify([_enrichir(i) for i in invs])


@api.route("/real/investments", methods=["POST"])
def post_real_investment():
    """Ajouter un investissement réel."""
    from utils.real_portfolio_db import ajouter_investissement, initialiser_real_db
    initialiser_real_db()
    data = request.get_json() or {}
    required = ("asset", "holding_type", "instrument_type", "entry_price", "quantity", "invested_amount")
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Champs manquants : {missing}"}), 400
    inv_id = ajouter_investissement(data)
    return jsonify({"id": inv_id, "saved": True})


@api.route("/real/investments/<int:inv_id>", methods=["PUT"])
def put_real_investment(inv_id):
    """Fermer une position (exit_price requis)."""
    from utils.real_portfolio_db import fermer_investissement
    data = request.get_json() or {}
    if "exit_price" not in data:
        return jsonify({"error": "exit_price requis"}), 400
    res = fermer_investissement(inv_id, float(data["exit_price"]), data.get("notes", ""))
    if res is None:
        return jsonify({"error": "Investissement introuvable"}), 404
    return jsonify(res)


@api.route("/real/investments/<int:inv_id>", methods=["DELETE"])
def delete_real_investment(inv_id):
    from utils.real_portfolio_db import supprimer_investissement
    ok = supprimer_investissement(inv_id)
    return jsonify({"deleted": ok})


@api.route("/real/advice")
def get_real_advice():
    """Conseils actifs (non répondus)."""
    from utils.real_portfolio_db import lire_conseils_actifs
    return jsonify(lire_conseils_actifs())


@api.route("/real/advice/<int:advice_id>/respond", methods=["POST"])
def post_advice_response(advice_id):
    from utils.real_portfolio_db import enregistrer_decision_user
    data = request.get_json() or {}
    decision = data.get("decision", "")
    ok = enregistrer_decision_user(advice_id, decision)
    return jsonify({"recorded": ok})


@api.route("/real/refresh-advice", methods=["POST"])
def post_refresh_advice():
    """Force l'évaluation manuelle de tout le portefeuille réel."""
    from agents.real_advisor import evaluer_tout_le_portefeuille
    nb = evaluer_tout_le_portefeuille()
    return jsonify({"conseils_crees": nb})


# ── v5.1 : Budget réel ────────────────────────────────────────────────────

@api.route("/real/budget")
def get_real_budget():
    """Résumé complet du budget réel + répartition par catégorie."""
    from utils.real_portfolio_db import initialiser_real_db
    from utils.real_vue import budget_reel_vue
    initialiser_real_db()
    return jsonify(budget_reel_vue())


@api.route("/real/budget", methods=["PUT"])
def put_real_budget():
    """Modifier le capital total réel."""
    from utils.real_portfolio_db import set_budget_capital, initialiser_real_db
    initialiser_real_db()
    data = request.get_json() or {}
    if "total_capital" not in data:
        return jsonify({"error": "total_capital requis"}), 400
    set_budget_capital(float(data["total_capital"]))
    return jsonify({"saved": True})
