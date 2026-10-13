"""
dashboard/api/jev_fantome_routes.py — Fantôme Jev au dashboard (REGISTRE_CRITERES §8.3,
v1.5), descriptif, pas un critère :
- GET /api/jev/fantome         : ligne de comparaison fantôme / paper (page d'accueil) ;
- GET /api/jev/fantome/detail  : les quatre blocs de la page détaillée ;
- GET /fantome-jev             : la page détaillée.

LECTURE SEULE : GET uniquement (Flask répond 405 à tout autre verbe), base ouverte
en mode=ro, aucune écriture.
"""

from flask import Blueprint, jsonify, render_template

from utils.jev_db import connexion_lecture
from utils.jev_fantome_page import page
from utils.jev_paper_comparaison import MENTION, comparaison
from utils.logger import get_logger

logger = get_logger(__name__)

jev_fantome_api = Blueprint("jev_fantome_api", __name__, url_prefix="/api/jev")
jev_fantome_page = Blueprint("jev_fantome_page", __name__)


def _lire(calcul, quoi: str):
    try:
        conn = connexion_lecture()
        try:
            return jsonify(calcul(conn))
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Fantôme Jev : {quoi} indisponible : {e}")
        return jsonify({"error": f"{quoi} indisponible", "mention": MENTION}), 500


@jev_fantome_api.route("/fantome")
def get_jev_fantome():
    return _lire(comparaison, "comparaison")


@jev_fantome_api.route("/fantome/detail")
def get_jev_fantome_detail():
    return _lire(page, "page détaillée")


@jev_fantome_page.route("/fantome-jev")
def page_fantome_jev():
    return render_template("fantome_jev.html", page="fantome_jev")
