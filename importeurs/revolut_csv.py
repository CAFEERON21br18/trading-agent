"""Import du relevé CSV Revolut vers le grand livre.

La lecture du fichier est dans revolut_lecture.py (format générique, COLONNES à ajuster sur
le vrai relevé). Ici : l'aperçu, qui ne fait que lire, et l'import, tout ou rien : une
ligne illisible et rien n'est écrit. Réimporter le même fichier n'ajoute aucun doublon.
Les achats et ventes deviennent des trades ; DIVIDEND, CASH TOP-UP et CASH WITHDRAWAL
deviennent des mouvements ; les autres types sont ignorés et comptés.
"""
from ledger import ecriture, lecture

from .revolut_lecture import (COLONNES, MOUVEMENTS, LigneMouvement, LigneTrade,  # noqa: F401
                              Rapport, lire, nombre)

SOURCE = "revolut_csv"
COMPTE = "Revolut"


def apercu(conn, flux, colonnes: dict = COLONNES) -> Rapport:
    """Lit le relevé et compte ce qu'un import ajouterait. N'écrit rien.

    conn : grand livre ouvert en lecture (ledger.ouvrir_lecture), ou None s'il n'existe pas
    encore : tout est alors à ajouter.
    """
    trades, mouvements, rapport = lire(flux, colonnes)
    for lignes, table, ajout, present in (
            (trades, "trades", "importes", "deja_presents"),
            (mouvements, "mouvements", "mouvements_importes", "mouvements_deja_presents")):
        connues = lecture.references_presentes(conn, table, SOURCE) if conn else set()
        deja = sum(1 for ligne in lignes if ligne.ref_source in connues)
        setattr(rapport, present, deja)
        setattr(rapport, ajout, len(lignes) - deja)
    return rapport


def importer_flux(conn, flux, compte_nom: str = COMPTE, devise_compte: str = "EUR",
                  colonnes: dict = COLONNES) -> Rapport:
    """Importe un relevé déjà ouvert (fichier ou texte en mémoire). Rien n'est écrit s'il y a
    une erreur."""
    trades, mouvements, rapport = lire(flux, colonnes)
    if rapport.erreurs:
        return rapport
    try:
        compte_id = ecriture.compte(conn, compte_nom, "reel", devise_compte)
        for t in trades:
            instrument_id = ecriture.instrument(conn, t.symbole, t.devise)
            cree = ecriture.enregistrer_trade(
                conn, compte_id=compte_id, instrument_id=instrument_id,
                horodatage=t.horodatage, sens=t.sens, quantite=t.quantite,
                prix=t.prix, devise=t.devise, source=SOURCE,
                ref_source=t.ref_source, taux_change=t.taux,
                couts=[("commission", t.frais)] if t.frais > 0 else ())
            if cree is None:
                rapport.deja_presents += 1
            else:
                rapport.importes += 1
        for m in mouvements:
            instrument_id = (ecriture.instrument(conn, m.symbole, m.devise)
                             if m.symbole else None)
            cree = ecriture.enregistrer_mouvement(
                conn, compte_id=compte_id, horodatage=m.horodatage, type_=m.type,
                montant=m.montant, devise=m.devise, source=SOURCE,
                ref_source=m.ref_source, instrument_id=instrument_id)
            if cree is None:
                rapport.mouvements_deja_presents += 1
            else:
                rapport.mouvements_importes += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport


def importer(conn, chemin: str, compte_nom: str = COMPTE,
             devise_compte: str = "EUR", colonnes: dict = COLONNES) -> Rapport:
    """Importe le relevé dans le grand livre. Rien n'est écrit s'il y a une erreur."""
    with open(chemin, newline="", encoding="utf-8-sig") as flux:
        return importer_flux(conn, flux, compte_nom, devise_compte, colonnes)
