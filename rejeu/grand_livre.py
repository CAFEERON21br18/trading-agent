"""
rejeu/grand_livre.py — Le grand livre du rejeu : data/rejeu/ledger_rejeu.db.

Même schéma que le grand livre de TradingX, mais un AUTRE fichier : rien n'est jamais écrit dans
data/ledger.db. Écritures par les seules fonctions de ledger/ecriture.py. Un compte par
configuration (capital, profil de frais) et par nature (rejeu, référence annuelle, référence de
période) ; chaque ordre exécuté est un trade avec ses frais ; la valeur du compte à la clôture de
chaque jour est dans valeur_quotidienne. Montants en euros (1 € = 1 $, comme le paper trader).
Un nouveau lancement n'efface rien : le grand livre précédent, son résumé, son rapport et les
bases jetables de l'agent sont déplacés dans archives/, horodatés.
"""

import os
import shutil
from datetime import date
from decimal import Decimal

import ledger
import mesures
from ledger import ecriture
from rejeu import frais
from rejeu import parametres as P
from rejeu.resultat import Resultat

SOURCE = "rejeu"
FICHIER = "ledger_rejeu.db"
TYPE_COMPTE = "demo"  # ni argent réel ni paper de l'agent : une simulation
A_ARCHIVER = (FICHIER, "lancement.json")


def chemin(dossier: str | None = None) -> str:
    return os.path.join(dossier or P.DOSSIER, FICHIER)


def archiver(horodatage: str, dossier: str | None = None, dossier_rapport: str | None = None) -> list[str]:
    """Déplace les sorties du lancement précédent dans archives/ (rien n'est effacé)."""
    deplaces = []
    donnees = dossier or P.DOSSIER
    bases = tuple(sorted(n for n in (os.listdir(donnees) if os.path.isdir(donnees) else [])
                         if n.startswith("agent_") and ".db" in n))  # positions du lancement précédent
    for racine, noms in ((donnees, A_ARCHIVER + bases), (dossier_rapport or P.DOSSIER_RAPPORT, ("RAPPORT.md",))):
        for nom in noms:
            source = os.path.join(racine, nom)
            if os.path.isfile(source):
                base, extension = os.path.splitext(nom)
                cible = os.path.join(racine, "archives", f"{base}_{horodatage}{extension}")
                os.makedirs(os.path.dirname(cible), exist_ok=True)
                shutil.move(source, cible)
                deplaces.append(cible)
    return deplaces


def ecrire(conn, resultat: Resultat) -> int:
    """Inscrit les ordres et les valeurs quotidiennes d'une simulation. Rend l'id du compte."""
    compte_id = ecriture.compte(conn, resultat.compte, TYPE_COMPTE, P.DEVISE)
    instruments = {}
    for o in resultat.ordres:
        if o.ticker not in instruments:
            instruments[o.ticker] = ecriture.instrument(conn, o.ticker, P.DEVISE, classe=frais.type_titre(o.ticker))
        contexte = None
        if o.stop is not None:  # ordre d'entrée de la stratégie : stop initial, pour le résultat en R
            contexte = {"bras": "regles", "stop_initial": frais.decimal(o.stop) if o.stop > 0 else None, "note": o.style}
        elif o.statut:
            contexte = {"note": o.statut}  # ordre de sortie : ce qui l'a déclenché
        ecriture.enregistrer_trade(
            conn, compte_id=compte_id, instrument_id=instruments[o.ticker], horodatage=o.quand, sens=o.sens,
            quantite=frais.decimal(o.quantite), prix=frais.decimal(o.prix), devise=P.DEVISE, source=SOURCE,
            ref_source=f"{resultat.compte}|{o.ref}", couts=list(o.frais), contexte=contexte)
    for jour, valeur in resultat.valeurs:
        ecriture.enregistrer_valeur(conn, compte_id, jour, valeur, P.DEVISE)
    return compte_id


def comptes(conn) -> dict[str, int]:
    return {c.nom: c.id for c in ledger.comptes(conn)}


def trades(conn, compte_id: int) -> list:
    """Trades clos du compte, reconstruits par mesures (premier entré, premier sorti)."""
    return mesures.reconstruire(ledger.executions_actives(conn, compte_id))[0]


def positions_ouvertes(conn, compte_id: int) -> list:
    return mesures.reconstruire(ledger.executions_actives(conn, compte_id))[1]


def valeurs(conn, compte_id: int) -> list[tuple[date, Decimal]]:
    return ledger.valeurs_quotidiennes(conn, compte_id)


def sorties_par_motif(conn, compte_id: int) -> dict[str, int]:
    """Nombre d'ordres de sortie par motif (CLOSED_SL, CLOSED_TP, CLOSED_REVERSAL…)."""
    return {l[0]: l[1] for l in conn.execute(
        "SELECT c.note, COUNT(*) FROM trades t JOIN contexte_entree c ON c.trade_id = t.id"
        " WHERE t.compte_id = ? AND c.stop_initial IS NULL AND c.bras IS NULL GROUP BY c.note ORDER BY c.note",
        (compte_id,))}
