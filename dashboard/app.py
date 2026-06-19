"""
dashboard/app.py — Application Flask AlphaSignal
PWA mobile-first accessible sur le réseau Wi-Fi local.
Démarrage : python dashboard/app.py → http://<IP_Mac>:5000
"""

import sys
import os
from flask import Flask, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api.routes import api
from utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.register_blueprint(api)


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
    # host=0.0.0.0 → accessible depuis tout appareil sur le Wi-Fi local
    # port=8080 → évite le conflit avec AirPlay Receiver sur macOS (port 5000)
    PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
    logger.info(f"Dashboard AlphaSignal — démarrage sur http://0.0.0.0:{PORT}")
    logger.info(f"Accès local : http://localhost:{PORT}")
    logger.info(f"Accès Wi-Fi (téléphone) : http://192.168.1.171:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
