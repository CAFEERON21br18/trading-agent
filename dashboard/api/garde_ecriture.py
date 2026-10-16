"""
dashboard/api/garde_ecriture.py — Routes modifiantes réservées au JavaScript du dashboard.

N'importe quelle page web ouverte dans le navigateur du PC ou du téléphone peut envoyer un POST
« simple » (sans corps, ou en text/plain, sans en-tête personnalisé) vers 127.0.0.1:8080 ou
l'adresse du tailnet : le navigateur l'envoie sans rien demander, et le dashboard n'a pas
d'authentification. Toute requête POST, PUT, PATCH ou DELETE doit donc porter l'en-tête
X-AlphaSignal: 1. Un en-tête personnalisé oblige le navigateur à demander d'abord la permission
(requête OPTIONS, CORS), que le dashboard n'accorde jamais. Sans lui : 403. Les GET ne changent pas.
Le JavaScript des pages l'ajoute à chaque fetch modifiant (dashboard/templates/base.html).
"""

from flask import jsonify, request

EN_TETE = "X-AlphaSignal"
METHODES_MODIFIANTES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def exiger_en_tete():
    """before_request de l'application : None pour laisser passer, sinon la réponse 403."""
    if request.method in METHODES_MODIFIANTES and request.headers.get(EN_TETE) != "1":
        return jsonify({"error": f"en-tête {EN_TETE}: 1 requis pour {request.method}"}), 403
    return None
