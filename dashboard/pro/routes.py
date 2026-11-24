"""
dashboard/pro/routes.py — Pages du dashboard professionnel (blueprint « pro »).

- GET /pro : « Vue d'ensemble », un panneau par compte, jamais additionnés.
LECTURE SEULE : ces pages ouvrent le grand livre (data/ledger.db) et la base de l'agent en
mode=ro et n'écrivent rien. La devise d'affichage (EUR ou USD) et la période du compte paper
sont retenues dans l'URL. Les journaux ne reçoivent aucune valeur lue, seulement le type
d'une erreur.
"""

from datetime import date, datetime, timezone

from flask import Blueprint, render_template, request
from markupsafe import Markup

from dashboard.pro import comptes, donnees, vue_ensemble
from utils.logger import get_logger

logger = get_logger(__name__)

pro = Blueprint("pro", __name__)


def aujourd_hui() -> date:
    """Jour de la lecture (UTC), pour l'âge des prix et le taux de la bascule."""
    return datetime.now(timezone.utc).date()


def parametres() -> tuple[str, str]:
    """(devise d'affichage, période) lues dans l'URL ; une valeur inconnue revient au défaut."""
    devise = request.args.get("devise", "EUR").upper()
    periode = request.args.get("periode", "tout")
    return (devise if devise in donnees.DEVISES else "EUR",
            periode if periode in donnees.PERIODES else "tout")


@pro.route("/pro")
def page_vue():
    devise, periode = parametres()
    erreur = ""
    try:
        contexte = vue_ensemble.vue(comptes.LEDGER, comptes.base_agent(), devise, periode, aujourd_hui())
        for panneau in contexte["panneaux"]:
            panneau["courbe"] = Markup(panneau["courbe"])  # SVG écrit par courbe_svg.py, textes échappés
    except Exception as e:
        logger.error(f"Dashboard pro : vue d'ensemble illisible ({type(e).__name__})")
        contexte = vue_ensemble.vue_sans_lecture(devise, periode)
        erreur = "Le grand livre n'a pas pu être lu. Aucun chiffre n'est affiché."
    return render_template("pro_vue.html", page="pro", erreur=erreur, **contexte)
