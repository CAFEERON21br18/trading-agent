"""
dashboard/api/routes.py — Endpoints JSON du dashboard
Lecture seule (V1) sauf endpoints POST déclarés explicitement.
"""

import sys
import os
import subprocess
import threading
from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.api import queries
from utils.logger import get_logger

logger = get_logger(__name__)
api = Blueprint("api", __name__, url_prefix="/api")


@api.route("/portfolio")
def get_portfolio():
    return jsonify(queries.portfolio_resume())


@api.route("/portfolio/history")
def get_portfolio_history():
    limite = int(request.args.get("limit", 90))
    return jsonify(queries.equity_curve(limite))


@api.route("/positions")
def get_positions():
    status = request.args.get("status")
    asset_type = request.args.get("type")
    return jsonify(queries.positions(filtre_status=status, filtre_type=asset_type))


@api.route("/positions/<int:pos_id>")
def get_position(pos_id):
    pos = queries.position_detail(pos_id)
    if not pos:
        return jsonify({"error": "Position non trouvée"}), 404
    return jsonify(pos)


@api.route("/watchlist")
def get_watchlist():
    return jsonify(queries.watchlist())


@api.route("/journal")
def get_journal():
    limite = int(request.args.get("limit", 50))
    return jsonify(queries.journal_trades(limite))


@api.route("/performance")
def get_performance():
    return jsonify(queries.performance_globale())


@api.route("/memory/lessons")
def get_lessons():
    return jsonify({"contenu": queries.fichier_memoire("lessons_learned.md")})


@api.route("/memory/patterns")
def get_patterns():
    return jsonify({"contenu": queries.fichier_memoire("market_patterns.md")})


@api.route("/memory/performance")
def get_perf_md():
    return jsonify({"contenu": queries.fichier_memoire("performance_tracker.md")})


@api.route("/memory/journal")
def get_trade_journal_md():
    return jsonify({"contenu": queries.fichier_memoire("trade_journal.md")})


@api.route("/health")
def get_health():
    return jsonify(queries.health())


@api.route("/explorers/queue")
def get_explorer_queue():
    """File de découvertes des 7 explorateurs (triée par score)."""
    from agents.explorers.queue_manager import lire_queue
    return jsonify(lire_queue())


@api.route("/budget")
def get_budget():
    """État du Budget Manager : mode + allocation + diagnostic."""
    from agents.budget_manager.strategy import detecter_mode, parametres_mode, capital_investissable, diagnostic
    from utils.portfolio_db import lire_positions_ouvertes
    import config as _cfg

    mode = detecter_mode()
    cap_inv = capital_investissable(mode)
    positions = lire_positions_ouvertes()
    investi = sum(p["invested_amount"] for p in positions)

    return jsonify({
        "mode":                  mode,
        "parametres":            parametres_mode(mode),
        "capital_total":         _cfg.CAPITAL,
        "capital_investissable": cap_inv,
        "reserve":               _cfg.CAPITAL - cap_inv,
        "investi":               investi,
        "cash_disponible":       cap_inv - investi,
        "diagnostic":            diagnostic(),
        "positions":             positions,
    })


@api.route("/intuition")
def get_intuition():
    """Stats du suivi d'intuition."""
    from agents.trade_journalist.intuition_tracker import stats_intuition
    return jsonify(stats_intuition())


# ── v5.0 — Portefeuille RÉEL ─────────────────────────────────────────────

@api.route("/real/portfolio")
def get_real_portfolio():
    """Résumé du portefeuille réel."""
    from utils.real_portfolio_db import resume_portefeuille
    return jsonify(resume_portefeuille())


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
    from utils.real_portfolio_db import get_real_budget_summary, initialiser_real_db
    initialiser_real_db()
    return jsonify(get_real_budget_summary())


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


@api.route("/plans", methods=["POST"])
def post_plan():
    from utils.real_portfolio_db import creer_plan
    data = request.get_json() or {}
    if not data.get("name") or not data.get("plan_type"):
        return jsonify({"error": "name et plan_type requis"}), 400
    return jsonify({"id": creer_plan(data), "saved": True})


@api.route("/plans/<int:plan_id>", methods=["PUT"])
def put_plan(plan_id):
    from utils.real_portfolio_db import modifier_plan
    data = request.get_json() or {}
    return jsonify({"updated": modifier_plan(plan_id, data)})


@api.route("/plans/<int:plan_id>", methods=["DELETE"])
def delete_plan(plan_id):
    from utils.real_portfolio_db import supprimer_plan
    return jsonify({"deleted": supprimer_plan(plan_id)})


@api.route("/plans/<int:plan_id>/progress")
def get_plan_progress(plan_id):
    from utils.real_portfolio_db import progression_plan
    return jsonify(progression_plan(plan_id))


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


@api.route("/real/calibrate", methods=["POST"])
def post_real_calibrate():
    """Calibre le prix d'un ticker sur celui affiché par Revolut."""
    from utils.real_price import calibrate_to_revolut
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").strip().upper()
    revolut_price = data.get("revolut_price")
    if not ticker or revolut_price is None:
        return jsonify({"error": "ticker et revolut_price requis"}), 400
    return jsonify(calibrate_to_revolut(ticker, float(revolut_price)))


@api.route("/real/calibrate/<ticker>")
def get_real_calibration(ticker):
    """Lit le facteur de calibration courant pour un ticker."""
    from utils.real_price import get_calibration, get_current_price
    cal = get_calibration(ticker.strip().upper())
    current = get_current_price(ticker.strip().upper())
    return jsonify({"calibration": cal, "current": current})


@api.route("/real/investments/<int:inv_id>/attach-plan", methods=["POST"])
def post_attach_plan(inv_id):
    """Rattacher une position réelle à un plan."""
    from utils.real_portfolio_db import rattacher_position_plan
    data = request.get_json() or {}
    return jsonify({"updated": rattacher_position_plan(inv_id, data.get("plan_id"))})


@api.route("/chat/create-plan", methods=["POST"])
def post_chat_create_plan():
    """Mode chat conversationnel pour créer un plan."""
    from agents.chat.plan_builder import etape_creation_plan
    data = request.get_json() or {}
    return jsonify(etape_creation_plan(data.get("session_id", "default"), data.get("message", "")))


# ── v5.0 — Chat stratégique ───────────────────────────────────────────────

@api.route("/chat/message", methods=["POST"])
def post_chat_message():
    from agents.chat.chat_engine import repondre
    data = request.get_json() or {}
    q = (data.get("message") or "").strip()
    if not q:
        return jsonify({"error": "Message vide"}), 400
    return jsonify(repondre(q))


@api.route("/chat/history")
def get_chat_history():
    from agents.chat.chat_engine import historique
    return jsonify(historique())


@api.route("/chat/history", methods=["DELETE"])
def delete_chat_history():
    from agents.chat.chat_engine import vider_historique
    return jsonify({"cleared": vider_historique()})


@api.route("/asset/<ticker>")
def get_asset(ticker):
    """Données détaillées d'un actif : prix récents + dernier signal + position ouverte."""
    from utils.indicators import charger_ohlcv
    df = charger_ohlcv(ticker, "1d", limite=90)
    prix = []
    if not df.empty:
        for ts, row in df.iterrows():
            prix.append({"date": str(ts)[:10], "close": float(row["Close"])})
    from utils.portfolio_db import lire_position_ouverte_actif
    pos = lire_position_ouverte_actif(ticker)
    return jsonify({"ticker": ticker, "prix": prix, "position_ouverte": pos})


# ── Endpoints d'action (POST) ──────────────────────────────────────────────

@api.route("/run-analysis", methods=["POST"])
def post_run_analysis():
    """Lance la routine en arrière-plan (réponse immédiate)."""
    def _run():
        try:
            from agents.orchestrator import lancer_routine_quotidienne
            lancer_routine_quotidienne(envoyer_emails=True)
        except Exception as e:
            logger.error(f"Run analysis manuel échoué : {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True, "message": "Routine lancée en arrière-plan"})


@api.route("/settings/watchlist", methods=["POST"])
def post_watchlist():
    """Met à jour data/watchlist.json (le format doit rester valide)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Body JSON manquant"}), 400
    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "watchlist.json",
    )
    try:
        import json as _json
        with open(chemin, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
        return jsonify({"saved": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
