"""
dashboard/api/routes.py — Endpoints JSON du dashboard
Lecture seule (V1) sauf endpoints POST déclarés explicitement.
Portefeuille réel : routes_reel.py et routes_reel_saisie.py ; plans : routes_plans_suivi.py et
plans_routes.py ; chat : routes_chat.py.
"""

import sys
import os
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


@api.route("/watchlist")
def get_watchlist():
    from dashboard.api.watchlist_io import reponse_sans_tri
    return reponse_sans_tri(queries.watchlist())  # P14 : ordre du fichier (jsonify trie les clés)


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


@api.route("/calendar")
def get_calendar():
    """v5.5.4 — Calendrier économique : macro + earnings de la watchlist."""
    from agents.technical_skills.economic_calendar import evenements_a_surveiller
    from utils.helpers import charger_watchlist, tous_les_tickers
    tickers = []
    try:
        tickers = tous_les_tickers(charger_watchlist())
    except Exception:
        pass
    jours = int(request.args.get("jours", 14))
    return jsonify(evenements_a_surveiller(tickers, jours_avant=jours))


@api.route("/correlation")
def get_correlation():
    """v5.5.3 — Matrice de corrélation du portefeuille paper OPEN + alertes."""
    from agents.technical_skills.correlation import correlation_portefeuille
    return jsonify(correlation_portefeuille())


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
            from utils.registre_manuel import ROUTE_ANALYSE
            lancer_routine_quotidienne(envoyer_emails=True, declencheur=ROUTE_ANALYSE)  # registre : « manuel » (R3)
        except Exception as e:
            logger.error(f"Run analysis manuel échoué : {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True, "message": "Routine lancée en arrière-plan"})


@api.route("/settings/watchlist/actif", methods=["POST"])
def post_watchlist_actif():
    """P14 (TODO §16) : active ou désactive un seul actif ; le reste du fichier ne change pas.
    Body : {"categorie": "crypto", "ticker": "BTC-USD", "actif": true|false}."""
    d = request.get_json() or {}
    if not d.get("categorie") or not d.get("ticker") or not isinstance(d.get("actif"), bool):
        return jsonify({"error": "categorie, ticker et actif (booléen) requis"}), 400
    try:
        from utils.registre import composition_watchlist
        from utils.registre_manuel import noter_watchlist, ROUTE_WATCHLIST_ACTIF
        from dashboard.api.watchlist_io import basculer_actif, CHEMIN
        avant = composition_watchlist()
        erreur = basculer_actif(CHEMIN, d["categorie"], d["ticker"], d["actif"])
        if erreur:
            return jsonify({"error": erreur}), 404
        noter_watchlist(avant, ROUTE_WATCHLIST_ACTIF)  # registre (Phase 4, R3) : cycle « manuel »
        return jsonify({"saved": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Les autres routes du blueprint « api » sont dans quatre modules (règle des 200 lignes) : les importer
# ici, après la création de « api », les enregistre. Import en fin de fichier : ces modules importent
# « api » depuis celui-ci.
from dashboard.api import routes_reel, routes_reel_saisie, routes_plans_suivi, routes_chat  # noqa: E402,F401
