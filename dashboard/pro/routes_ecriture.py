"""
dashboard/pro/routes_ecriture.py — Les seules routes du dashboard professionnel qui écrivent.

- POST /pro/import/apercu    : relevé CSV Revolut reçu dans le corps de la requête, lu en mémoire,
  comparé au grand livre en lecture seule. Rien n'est écrit. S'il est importable, un jeton à
  usage unique (10 minutes) garde son contenu en mémoire du serveur ;
- POST /pro/import/confirmer : écrit le relevé désigné par le jeton, par les fonctions de
  ledger/ecriture.py (via importeurs/revolut_csv.py). Tout ou rien.
Mêmes protections que les autres routes modifiantes du dashboard : méthode POST et en-tête
X-AlphaSignal: 1 (dashboard/api/garde_ecriture.py, appliqué à toute l'application). Le fichier
n'est jamais enregistré sur le disque : il est lu dans le corps brut, sans formulaire multipart
(Werkzeug écrirait un gros fichier de formulaire dans un fichier temporaire). Les réponses sont
du JSON, que la page insère avec escHtml. Rien du relevé ne va dans les journaux.
"""

from flask import jsonify, request

from dashboard.pro import comptes, import_releve, jetons
from dashboard.pro.routes import pro
from utils.logger import get_logger

logger = get_logger(__name__)

EXPIRE = "aperçu expiré ou déjà utilisé : renvoyer le fichier"


@pro.route("/pro/import/apercu", methods=["POST"])
def post_import_apercu():
    """Temps 1 : aperçu. Ne modifie ni le grand livre ni le disque."""
    if request.mimetype.startswith("multipart/") or request.mimetype == "application/x-www-form-urlencoded":
        return jsonify({"error": "envoyer le fichier CSV dans le corps de la requête, sans formulaire"}), 415
    if (request.content_length or 0) > import_releve.TAILLE_MAX:
        return jsonify({"error": "fichier trop volumineux : 2 Mo au plus"}), 413
    try:
        texte = import_releve.decoder(request.stream.read(import_releve.TAILLE_MAX + 1))
        resume = import_releve.apercu(texte, comptes.LEDGER)
    except import_releve.ReleveRefuse as refus:
        return jsonify({"error": str(refus)}), 400
    except Exception as e:
        logger.error(f"Dashboard pro : aperçu du relevé en échec ({type(e).__name__})")
        return jsonify({"error": "aperçu impossible : le grand livre n'a pas pu être lu"}), 500
    # une erreur dans le fichier, ou rien à ajouter : pas de jeton, donc pas de confirmation possible
    resume["jeton"] = jetons.en_attente.deposer(texte) if resume["confirmable"] else None
    return jsonify(resume)


@pro.route("/pro/import/confirmer", methods=["POST"])
def post_import_confirmer():
    """Temps 2 : écriture du relevé vu à l'aperçu, désigné par son jeton."""
    jeton = (request.get_json(silent=True) or {}).get("jeton")
    texte = jetons.en_attente.retirer(jeton) if isinstance(jeton, str) else None
    if texte is None:
        return jsonify({"error": EXPIRE}), 410
    try:
        with comptes.VERROU_ECRITURE:
            resume = import_releve.confirmer(texte, comptes.LEDGER)
    except Exception as e:
        logger.error(f"Dashboard pro : import du relevé en échec ({type(e).__name__})")
        return jsonify({"error": "import impossible : rien n'a été écrit"}), 500
    return jsonify(resume), (200 if resume["ecrit"] else 409)
