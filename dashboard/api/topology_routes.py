"""
dashboard/api/topology_routes.py — GET /api/topology : carte de l'agent (Phase 3).

LECTURE SEULE : un seul GET (Flask répond 405 à tout autre verbe). Ne lit ni
la base ni le registre ; seulement graphify-out/graph.json et le code source.
Résultat gardé en mémoire tant que graph.json et le commit HEAD ne changent pas.

Prérequis (machine sans Graphify, ex. la tour au premier passage) :
  .venv\\Scripts\\pip.exe install -r requirements-dev.txt
  .venv\\Scripts\\graphify.exe extract . --code-only
Sans graph.json, la route répond 503 avec ces instructions.
"""

import os
import threading

from flask import Blueprint, jsonify

from dashboard.api.topology_build import construire_topologie
from dashboard.api.topology_sources import commit_head
from utils.logger import get_logger

logger = get_logger(__name__)

topology_api = Blueprint("topology_api", __name__, url_prefix="/api")

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRAPHE = os.path.join(RACINE, "graphify-out", "graph.json")
AIDE = [
    r".venv\Scripts\pip.exe install -r requirements-dev.txt",
    r".venv\Scripts\graphify.exe extract . --code-only",
]

_cache = {"cle": None, "carte": None}
_verrou = threading.Lock()


def carte_en_cache():
    """Carte recalculée seulement si graph.json ou HEAD ont changé."""
    cle = (os.path.getmtime(GRAPHE), commit_head(RACINE))
    with _verrou:
        if _cache["cle"] != cle:
            _cache["carte"] = construire_topologie(RACINE, GRAPHE)
            _cache["cle"] = cle
        return _cache["carte"]


@topology_api.route("/topology", methods=["GET"])
def get_topology():
    if not os.path.isfile(GRAPHE):
        return jsonify({"erreur": "graphify-out/graph.json absent : carte du code non générée",
                        "aide": AIDE}), 503
    try:
        return jsonify(carte_en_cache())
    except Exception as e:
        logger.error(f"/api/topology : {e}", exc_info=True)
        return jsonify({"erreur": f"Construction de la carte impossible : {e}", "aide": AIDE}), 500
