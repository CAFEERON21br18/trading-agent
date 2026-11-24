"""
dashboard/api/routes_chat.py — Routes du chat stratégique : création de plan, message, historique.
Sorti de dashboard/api/routes.py (règle des 200 lignes). Mêmes routes, même blueprint « api » :
routes.py importe ce module en fin de fichier, ce qui enregistre les routes.
"""

from flask import jsonify, request

from dashboard.api.routes import api


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
