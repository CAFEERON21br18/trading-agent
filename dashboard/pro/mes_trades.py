"""
dashboard/pro/mes_trades.py — Contenu de la page « Mes trades » (/pro/trades) : le compte réel.

Positions ouvertes (avec leur dernier prix et les frais payés à l'achat), tous les trades clos
(brut, frais, net), les frais ordre par ordre, les mouvements d'argent. Le compte paper n'y
figure pas. Sans Flask : grand livre et base de l'agent ouverts en lecture seule, textes déjà
mis en forme, que le gabarit échappe. Un ordre réel sans frais détecté le dit : jamais « 0 ».
"""

from datetime import date
from decimal import Decimal

import ledger
import mesures
from dashboard.pro import (chiffres, comptes, donnees, formats, import_releve, latent, prix,
                           vue_ensemble)

FRAIS_NON_DETECTES = "frais non détectés"
TYPES = {"depot": ("Dépôt", 1), "retrait": ("Retrait", -1), "dividende": ("Dividende", 1)}


def _frais(couts: Decimal, montant: Decimal, devise: str) -> str:
    """Frais et leur part du montant de l'ordre, ou la mention « frais non détectés »."""
    if couts <= 0:
        return FRAIS_NON_DETECTES
    return f"{formats.montant(couts, devise)} · {formats.pourcent(couts / montant, 2)} du montant"


def ligne_position(ligne: latent.LigneLatente, devise: str, source: donnees.Source, aujourd_hui: date) -> dict:
    p = ligne.position
    if ligne.latent is None:
        dernier, resultat, classe = ligne.indisponible, formats.ABSENT, ""
    else:
        dernier = f"{formats.montant(ligne.prix.valeur, p.devise)} · {formats.jour(ligne.prix.jour)}"
        bloc = donnees.essayer([p.devise], devise, lambda: mesures.convertir(
            ligne.latent, p.devise, devise, aujourd_hui, source.taux))
        resultat = bloc.indisponible or formats.montant_signe(bloc.valeur, devise)
        classe = "" if bloc.indisponible else formats.classe(bloc.valeur)
    return {"titre": p.symbole, "sens": p.sens, "quantite": formats.quantite(p.quantite),
            "entree": f"{formats.montant(p.prix_entree, p.devise)} · {formats.jour(p.ouvert_le)}",
            "dernier": dernier, "latent": resultat, "classe": classe,
            "frais": _frais(p.couts, p.quantite * p.prix_entree, p.devise)}


def ligne_ordre(e) -> dict:
    montant = e.quantite * e.prix
    return {"le": formats.jour(e.horodatage), "titre": e.symbole, "sens": e.sens,
            "quantite": formats.quantite(e.quantite), "prix": formats.montant(e.prix, e.devise),
            "montant": formats.montant(montant, e.devise), "frais": _frais(e.couts, montant, e.devise)}


def ligne_mouvement(m) -> dict:
    libelle, signe = TYPES[m.type]
    return {"le": formats.jour(m.horodatage), "type": libelle, "titre": m.symbole or formats.ABSENT,
            "montant": formats.montant_signe(signe * m.montant, m.devise),
            "classe": formats.classe(signe * m.montant)}


def page_sans_lecture(devise: str) -> dict:
    """Contexte sans aucune donnée : pas de grand livre, ou lecture en échec."""
    return {"grand_livre": False, "devise": devise, "vide": True, "positions": [], "latent": None,
            "trades": [], "ordres": [], "mouvements": [], "titre_compte": comptes.REEL.titre,
            "taille_max": import_releve.TAILLE_MAX}


def page(chemin_ledger: str, chemin_base: str, devise: str, aujourd_hui: date) -> dict:
    """Contexte du gabarit pro_trades.html."""
    contexte = page_sans_lecture(devise)
    conn = ledger.ouvrir_lecture(chemin_ledger)
    if conn is None:
        return contexte
    try:
        source = comptes.source(conn, comptes.REEL)
    finally:
        conn.close()
    contexte["grand_livre"] = True
    if source is None or not (source.executions or source.mouvements):
        return contexte
    ouvertes = donnees.positions_ouvertes(source)
    valeur = latent.resultat_latent(source, devise, prix.derniers_prix(chemin_base, [o.symbole for o in ouvertes]),
                                    aujourd_hui)
    trades = donnees.lignes_trades(source, devise)
    contexte.update(
        vide=False,
        positions=[ligne_position(l, devise, source, aujourd_hui) for l in valeur.lignes],
        latent=chiffres.chiffre_latent(valeur, devise),
        trades=[vue_ensemble.ligne_trade(t, c, comptes.REEL.titre, devise) for t, c in reversed(trades)],
        ordres=[ligne_ordre(e) for e in reversed(source.executions)],
        mouvements=[ligne_mouvement(m) for m in reversed(source.mouvements)],
    )
    return contexte
