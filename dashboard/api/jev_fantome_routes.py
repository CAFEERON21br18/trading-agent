"""
dashboard/api/jev_fantome_routes.py — GET /api/jev/fantome : ligne de comparaison
fantôme Jev / paper actuel (REGISTRE_CRITERES §8.3), descriptif, pas un critère.

LECTURE SEULE : GET uniquement (Flask répond 405 à tout autre verbe), base ouverte
en mode=ro. Renvoie la valeur et le nombre de positions ouvertes de chacun, rien
d'autre (§8.3 : seule exception à l'affichage avant la lecture du §7).
"""

from flask import Blueprint, jsonify

from utils.jev_db import connexion_lecture
from utils.jev_paper_comparaison import MENTION, comparaison
from utils.logger import get_logger

logger = get_logger(__name__)

jev_fantome_api = Blueprint("jev_fantome_api", __name__, url_prefix="/api/jev")


@jev_fantome_api.route("/fantome")
def get_jev_fantome():
    try:
        conn = connexion_lecture()
        try:
            return jsonify(comparaison(conn))
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Comparaison fantôme Jev / paper indisponible : {e}")
        return jsonify({"error": "comparaison indisponible", "mention": MENTION}), 500
