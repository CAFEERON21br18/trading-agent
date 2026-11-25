"""
dashboard/pro/routes.py — Pages du dashboard professionnel (blueprint « pro »).

- GET /pro        : « Vue d'ensemble », un panneau par compte, jamais additionnés ;
- GET /pro/trades : « Mes trades », le compte réel en détail et l'import du relevé ;
- GET /pro/rejeu  : « Rejeu », le verdict du rejeu sur plusieurs années (grand livre du rejeu,
  data/rejeu/ledger_rejeu.db, lu en lecture seule ; la page ne lance rien).
Les routes qui écrivent (POST) sont dans routes_ecriture.py, importé en fin de fichier.
LECTURE SEULE ICI : ces pages ouvrent le grand livre (data/ledger.db) et la base de l'agent en
mode=ro et n'écrivent rien. La devise d'affichage (EUR ou USD) et la période du compte paper
sont retenues dans l'URL. Les journaux ne reçoivent aucune valeur lue, seulement le type
d'une erreur.
"""

from datetime import date, datetime, timezone

from flask import Blueprint, render_template, request
from markupsafe import Markup

from dashboard.pro import comptes, donnees, mes_trades, rejeu_vue, vue_ensemble
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


@pro.route("/pro/trades")
def page_trades():
    devise, _ = parametres()
    erreur = ""
    try:
        contexte = mes_trades.page(comptes.LEDGER, comptes.base_agent(), devise, aujourd_hui())
    except Exception as e:
        logger.error(f"Dashboard pro : page des trades illisible ({type(e).__name__})")
        contexte = mes_trades.page_sans_lecture(devise)
        erreur = "Le grand livre n'a pas pu être lu. Aucun chiffre n'est affiché."
    return render_template("pro_trades.html", page="pro", erreur=erreur, **contexte)


@pro.route("/pro/rejeu")
def page_rejeu():
    capital = request.args.get("capital", type=int)
    profil = request.args.get("profil", "")
    erreur = ""
    try:
        contexte = rejeu_vue.page(capital, profil)
        if contexte.get("courbe"):
            contexte["courbe"] = Markup(contexte["courbe"])  # écrit par courbe_rejeu.py, textes échappés
    except Exception as e:
        logger.error(f"Dashboard pro : page du rejeu illisible ({type(e).__name__})")
        contexte = rejeu_vue.page_sans_resultat()
        erreur = "Le grand livre du rejeu n'a pas pu être lu. Aucun chiffre n'est affiché."
    return render_template("pro_rejeu.html", page="pro", erreur=erreur, **contexte)


from dashboard.pro import routes_ecriture  # noqa: E402,F401  (enregistre les routes POST du blueprint)
