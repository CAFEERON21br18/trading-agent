"""
dashboard/pro/vue_ensemble.py — Contenu de la page « Vue d'ensemble » (/pro).

Un panneau par compte, « Réel (Revolut) » et « Paper (agent) », chacun calculé seul : aucun
total ne réunit les deux. Le tableau des derniers trades clos liste les deux comptes côte à
côte, avec leur nom, sans somme. Sans Flask : le grand livre est ouvert en lecture seule, la
base de l'agent aussi, et tout ce qui sort est du texte déjà mis en forme (plus la courbe SVG).
Le filtre de période ne s'applique qu'au compte paper.
"""

from datetime import date

import ledger
import mesures
from dashboard.pro import chiffres, comptes, courbe_svg, donnees, formats, latent, prix

DERNIERS_TRADES = 20
LIBELLES_PERIODE = {"tout": "tout", "correctif": "depuis le correctif du prix d'entrée"}


def non_converti(devise_trade: str) -> str:
    """Ce qui s'écrit à la place d'un montant qui n'a pas pu être basculé."""
    return donnees.raison_devise([devise_trade]) or donnees.TAUX_INDISPONIBLE


def ligne_trade(trade, converti, compte: str, devise: str) -> dict:
    """Une ligne de tableau. Les prix restent dans la devise de cotation du titre."""
    return {
        "clos_le": trade.clos_le, "titre": trade.symbole, "sens": trade.sens,
        "compte": compte,
        "entree": f"{formats.jour(trade.ouvert_le)} · {formats.montant(trade.prix_entree, trade.devise)}",
        "sortie": f"{formats.jour(trade.clos_le)} · {formats.montant(trade.prix_sortie, trade.devise)}",
        "quantite": formats.quantite(trade.quantite),
        "brut": formats.montant_signe(converti.pnl_brut, devise) if converti else non_converti(trade.devise),
        "frais": formats.montant(converti.couts, devise) if converti else non_converti(trade.devise),
        "net": formats.montant_signe(converti.pnl_net, devise) if converti else non_converti(trade.devise),
        "classe": formats.classe(converti.pnl_net) if converti else "",
        "r": formats.en_r(trade.r),
    }


def panneau(conn, affiche: comptes.Affiche, devise: str, periode: str, chemin_base: str,
            aujourd_hui: date) -> dict:
    """Tout ce que la page montre d'un compte. `vide` : le compte n'a encore rien."""
    p = {"cle": affiche.cle, "titre": affiche.titre, "vide": True, "chiffres": [], "courbe": "",
         "courbe_message": "", "apports": None, "dividendes": None, "lignes": []}
    source = comptes.source(conn, affiche) if conn is not None else None
    if source is None or not (source.executions or source.mouvements):
        return p
    ouvertes = donnees.positions_ouvertes(source, periode)
    cours = prix.derniers_prix(chemin_base, [o.symbole for o in ouvertes])
    valeur_latente = latent.resultat_latent(source, devise, cours, aujourd_hui, periode)
    serie = donnees.serie_cumulee(source, devise, periode)
    p.update(
        vide=False,
        chiffres=chiffres.cinq_chiffres(source, devise, periode, valeur_latente),
        courbe=courbe_svg.courbe(serie.valeur or [], devise,
                                 f"Résultat net réalisé cumulé, {affiche.titre}"),
        courbe_message=serie.indisponible or ("" if serie.valeur else "Aucun trade clos sur la période."),
        lignes=[ligne_trade(t, c, affiche.titre, devise)
                for t, c in donnees.lignes_trades(source, devise, periode)],
    )
    if affiche is comptes.REEL:
        p["apports"] = chiffres.mouvement(donnees.apports_nets(source, devise), "Apports nets", devise)
        p["dividendes"] = chiffres.mouvement(donnees.dividendes(source, devise), "Dividendes", devise)
    return p


def vue(chemin_ledger: str, chemin_base: str, devise: str, periode: str, aujourd_hui: date) -> dict:
    """Contexte du gabarit pro_vue.html."""
    conn = ledger.ouvrir_lecture(chemin_ledger)
    try:
        panneaux = [panneau(conn, a, devise, periode if a is comptes.PAPER else "tout",
                            chemin_base, aujourd_hui) for a in comptes.AFFICHES]
    finally:
        if conn is not None:
            conn.close()
    derniers = sorted((l for p in panneaux for l in p["lignes"]), key=lambda l: l["clos_le"], reverse=True)
    return {
        "grand_livre": conn is not None, "devise": devise, "periode": periode,
        "periodes": LIBELLES_PERIODE, "panneaux": panneaux, "derniers": derniers[:DERNIERS_TRADES],
        "seuil": mesures.MIN_TRADES,
    }


def vue_sans_lecture(devise: str, periode: str) -> dict:
    """Contexte minimal quand la lecture a échoué : la page s'affiche et le dit."""
    return {"grand_livre": True, "devise": devise, "periode": periode, "periodes": LIBELLES_PERIODE,
            "panneaux": [], "derniers": [], "seuil": mesures.MIN_TRADES}
