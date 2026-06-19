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
