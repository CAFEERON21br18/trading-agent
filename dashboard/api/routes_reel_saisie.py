"""
dashboard/api/routes_reel_saisie.py — Routes de saisie du portefeuille réel : aperçu de prix, saisie
simple ou exacte, correction d'entrée, calibration Revolut, rattachement à un plan.
Sorti de dashboard/api/routes.py (règle des 200 lignes). Mêmes routes, même blueprint « api » :
routes.py importe ce module en fin de fichier, ce qui enregistre les routes.
"""

from flask import jsonify, request

from dashboard.api.routes import api


# ── v5.3 : Saisie simplifiée + calibration Revolut ─────────────────────────

@api.route("/real/price-preview")
def get_real_price_preview():
    """Aperçu : récupère le prix historique pour ticker+date(+heure)."""
    from utils.real_price import get_historical_price
    ticker = request.args.get("ticker", "").strip().upper()
    date_str = request.args.get("date", "").strip()
    time_str = request.args.get("time")
    if not ticker or not date_str:
        return jsonify({"error": "ticker et date requis"}), 400
    amount = request.args.get("amount", type=float)
    info = get_historical_price(ticker, date_str, time_str or None)
    if not info.get("price"):
        return jsonify({"error": info.get("error", "Prix indisponible")}), 400
    out = dict(info)
    if amount:
        out["quantity"] = round(amount / info["price"], 6)
        out["invested_amount"] = amount
    return jsonify(out)


@api.route("/real/investments/simple", methods=["POST"])
def post_real_investment_simple():
    """Création d'investissement à partir de ticker+date+heure+montant."""
    from utils.real_portfolio_db import creer_investissement_simple, initialiser_real_db
    initialiser_real_db()
    data = request.get_json() or {}
    required = ("ticker", "date", "invested_amount", "holding_type", "instrument_type")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Champs requis : {missing}"}), 400
    res = creer_investissement_simple(
        ticker=data["ticker"].strip().upper(),
        date_str=data["date"],
        time_str=data.get("time"),
        invested_amount=float(data["invested_amount"]),
        holding_type=data["holding_type"],
        instrument_type=data["instrument_type"],
        plan_id=data.get("plan_id"),
        asset_name=data.get("asset_name"),
        thesis=data.get("investment_thesis"),
    )
    return jsonify(res), (200 if res.get("success") else 400)


@api.route("/real/investments/exact", methods=["POST"])
def post_real_investment_exact():
    """v5.3.2 — Saisie exacte : montant + quantité Revolut → prix d'entrée exact."""
    from utils.real_portfolio_db import creer_investissement_exact, initialiser_real_db
    initialiser_real_db()
    data = request.get_json() or {}
    required = ("ticker", "invested_amount", "quantity", "entry_date",
                "holding_type", "instrument_type")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Champs requis : {missing}"}), 400
    res = creer_investissement_exact(
        ticker=data["ticker"].strip().upper(),
        invested_amount=float(data["invested_amount"]),
        quantity=float(data["quantity"]),
        entry_date=data["entry_date"],
        holding_type=data["holding_type"],
        instrument_type=data["instrument_type"],
        plan_id=data.get("plan_id"),
        asset_name=data.get("asset_name"),
        thesis=data.get("investment_thesis"),
    )
    return jsonify(res), (200 if res.get("success") else 400)


@api.route("/real/investments/<int:inv_id>/fix-entry", methods=["POST"])
def post_real_fix_entry(inv_id):
    """v5.3.2 — Corrige le prix d'entrée d'une position via la quantité Revolut exacte."""
    from utils.real_portfolio_db import corriger_entree_avec_quantite
    data = request.get_json() or {}
    qty = data.get("real_quantity")
    if qty is None:
        return jsonify({"error": "real_quantity requis"}), 400
    return jsonify(corriger_entree_avec_quantite(inv_id, float(qty)))


@api.route("/real/calibrate", methods=["POST"])
def post_real_calibrate():
    """Calibre le prix d'un ticker sur celui affiché par Revolut."""
    from utils.real_vue import calibrer_vue
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").strip().upper()
    revolut_price = data.get("revolut_price")
    if not ticker or revolut_price is None:
        return jsonify({"error": "ticker et revolut_price requis"}), 400
    return jsonify(calibrer_vue(ticker, float(revolut_price), data.get("devise")))


@api.route("/real/investments/<int:inv_id>/attach-plan", methods=["POST"])
def post_attach_plan(inv_id):
    """Rattacher une position réelle à un plan."""
    from utils.real_portfolio_db import rattacher_position_plan
    data = request.get_json() or {}
    return jsonify({"updated": rattacher_position_plan(inv_id, data.get("plan_id"))})
