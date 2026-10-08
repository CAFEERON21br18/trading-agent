"""
dashboard/app.py — Application Flask AlphaSignal
PWA mobile-first. Écoute sur 127.0.0.1 par défaut (DASHBOARD_HOST) ;
accès téléphone via Tailscale Serve (scripts/setup_tailscale.py).
Démarrage : python dashboard/app.py → http://localhost:8080
"""

import sys
import os
from flask import Flask, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api.routes import api
from dashboard.api.audit_routes import audit_api
from dashboard.api.topology_routes import topology_api
from dashboard.api.jev_fantome_routes import jev_fantome_api
from utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.register_blueprint(api)
app.register_blueprint(audit_api)  # Phase 4 / C : consultation de message_audit (GET seulement)
app.register_blueprint(topology_api)  # Phase 3 : carte de l'agent (GET seulement, sans base)
app.register_blueprint(jev_fantome_api)  # REGISTRE §8.3 : ligne fantôme Jev / paper (GET seulement, mode=ro)


# ── Pages HTML ────────────────────────────────────────────────────────────────

@app.route("/")
def page_overview():
    return render_template("overview.html", page="overview")


@app.route("/portfolio")
def page_portfolio():
    return render_template("portfolio.html", page="portfolio")


@app.route("/watchlist")
def page_watchlist():
    return render_template("watchlist.html", page="watchlist")


@app.route("/journal")
def page_journal():
    return render_template("journal.html", page="journal")


@app.route("/memory")
def page_memory():
    return render_template("memory.html", page="memory")


@app.route("/settings")
def page_settings():
    return render_template("settings.html", page="settings")


@app.route("/explorers")
def page_explorers():
    return render_template("explorers.html", page="explorers")


@app.route("/budget")
def page_budget():
    return render_template("budget.html", page="budget")


@app.route("/real")
def page_real():
    return render_template("real.html", page="real")


@app.route("/chat")
def page_chat():
    return render_template("chat.html", page="chat")


@app.route("/plans")
def page_plans():
    return render_template("plans.html", page="plans")


@app.route("/architecture")
def page_architecture():
    return render_template("architecture.html", page="architecture")


@app.route("/manifest.json")
def manifest():
    """Manifest PWA — pour 'Ajouter à l'écran d'accueil' sur iPhone."""
    return app.send_static_file("manifest.json")


@app.route("/sw.js")
def service_worker():
    """Service worker minimal pour le statut 'installé' de la PWA."""
    return app.send_static_file("sw.js")


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # host=127.0.0.1 (défaut) → seul ce PC, et Tailscale Serve qui proxifie
    # vers 127.0.0.1, joignent le dashboard. Pas d'authentification : en
    # 0.0.0.0, tout appareil du Wi-Fi local pourrait écrire dans le chat.
    # port=8080 → évite le conflit avec AirPlay Receiver sur macOS (port 5000)
    HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
    logger.info(f"Dashboard AlphaSignal — démarrage sur http://{HOST}:{PORT}")
    logger.info(f"Accès local : http://localhost:{PORT}")
    logger.info("Accès téléphone : Tailscale Serve (scripts/setup_tailscale.py)")
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(f"Dashboard joignable hors de ce PC (DASHBOARD_HOST={HOST})")
    app.run(host=HOST, port=PORT, debug=False)
