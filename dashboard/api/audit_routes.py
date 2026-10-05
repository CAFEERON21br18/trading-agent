"""
dashboard/api/audit_routes.py — API de consultation de message_audit (Phase 4, partie C).

LECTURE SEULE, par conception : uniquement des GET (Flask répond 405 à tout
autre verbe). Aucune route d'écriture ni de suppression sur message_audit, ni
maintenant ni en partie D. La purge de rétention passe par le cycle cleanup.

  GET /api/audit/messages        liste légère + filtres + pagination
  GET /api/audit/messages/<id>   enregistrement complet (prompt, contexte…)
  GET /api/audit/stats           synthèse : total, par LLM, par jour sur 7 jours

Filtres de la liste : du, au (AAAA-MM-JJ, jours locaux inclus), source,
llm, erreur / actions / contournement (oui|non), page, par_page (≤ 200).
"""

from flask import Blueprint, jsonify, request

from utils.message_audit_query import lister_messages, lire_message, PAR_PAGE_DEFAUT
from utils.message_audit_stats import statistiques

audit_api = Blueprint("audit_api", __name__, url_prefix="/api/audit")

_OUI, _NON = {"oui", "true", "1"}, {"non", "false", "0"}


def _booleen(nom: str):
    v = (request.args.get(nom) or "").strip().lower()
    if not v:
        return None
    if v in _OUI:
        return True
    if v in _NON:
        return False
    raise ValueError(f"{nom} invalide : {v!r} (attendu : oui ou non)")


def _entier(nom: str, defaut: int) -> int:
    v = request.args.get(nom)
    if v in (None, ""):
        return defaut
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"{nom} invalide : {v!r} (entier attendu)")


@audit_api.route("/messages")
def get_audit_messages():
    try:
        filtres = {"du": request.args.get("du"), "au": request.args.get("au"),
                   "source": request.args.get("source"), "llm": request.args.get("llm"),
                   "erreur": _booleen("erreur"), "actions": _booleen("actions"),
                   "contournement": _booleen("contournement")}
        filtres = {k: v for k, v in filtres.items() if v not in (None, "")}
        return jsonify(lister_messages(filtres, _entier("page", 1),
                                       _entier("par_page", PAR_PAGE_DEFAUT)))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@audit_api.route("/messages/<int:audit_id>")
def get_audit_message(audit_id: int):
    r = lire_message(audit_id)
    if r is None:
        return jsonify({"error": f"Enregistrement #{audit_id} introuvable"}), 404
    return jsonify(r)


@audit_api.route("/stats")
def get_audit_stats():
    try:
        return jsonify(statistiques(request.args.get("source") or None))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
