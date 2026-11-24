"""Positions paper de l'agent (table positions de data/database.db) vers le grand livre.

La base de l'agent est ouverte en lecture seule ; seule la table positions est lue. Une position
fermée donne deux exécutions (entrée, sortie), une position ouverte une seule. ref_source est
bâtie sur l'identifiant de la position : relancer la synchronisation n'ajoute aucun doublon.
Tout ou rien : une position illisible et rien n'est écrit.

Positions « boucle » (colonne boucle, scripts/marquer_boucles.py) : jamais importées. Sans la
colonne, la synchronisation s'arrête. Une position déjà importée et marquée depuis est retirée
par annuler_trade : une ligne d'annulation, aucune suppression. Sa référence reste prise : si
elle était démarquée plus tard, elle ne serait pas réimportée.

Devise : le paper trader traite 1 € = 1 $ et la table n'a pas de devise. Chaque trade est
enregistré dans la devise de cotation de l'instrument (importeurs/devises.py). Frais : le paper
trader n'en compte aucun, donc aucun coût dans le grand livre ; les résultats paper sont bruts
de frais.
"""
import math
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ledger import ecriture

from .devises import devise_cotation, devise_incertaine

SOURCE = "paper_agent"
COMPTE = "Paper agent"
DEVISE_COMPTE = "EUR"
BRAS = "regles"
COLONNES = ("id", "ticker", "asset_type", "direction", "status", "entry_price", "entry_date",
            "quantity", "stop_loss", "exit_price", "exit_date", "boucle")


class SynchronisationImpossible(RuntimeError):
    """La base de l'agent ne permet pas la synchronisation : rien n'est importé."""


class ColonneBoucleAbsente(SynchronisationImpossible):
    """La colonne de marquage des positions « boucle » manque."""


@dataclass
class Rapport:
    positions: int = 0       # positions lues, hors « boucle »
    boucles: int = 0         # positions marquées « boucle », non importées
    importes: int = 0        # exécutions ajoutées au grand livre
    deja_presents: int = 0   # exécutions déjà inscrites
    annules: int = 0         # exécutions annulées : position marquée « boucle » depuis son import
    devises_incertaines: list[str] = field(default_factory=list)
    erreurs: list[tuple[int, str]] = field(default_factory=list)


def lire_positions(chemin_base: str) -> list[sqlite3.Row]:
    """Lit la table positions, base ouverte en lecture seule. S'arrête sans la colonne boucle."""
    if not os.path.exists(chemin_base):
        raise SynchronisationImpossible(f"base introuvable : {chemin_base}")
    conn = sqlite3.connect(Path(chemin_base).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        presentes = {ligne[1] for ligne in conn.execute("PRAGMA table_info(positions)")}
        if not presentes:
            raise SynchronisationImpossible(f"table positions absente de {chemin_base}")
        if "boucle" not in presentes:
            raise ColonneBoucleAbsente(
                "colonne « boucle » absente de la table positions : lancer d'abord"
                " scripts/marquer_boucles.py --appliquer. Rien n'a été importé.")
        manquantes = [c for c in COLONNES if c not in presentes]
        if manquantes:
            raise SynchronisationImpossible(f"colonnes absentes de positions : {manquantes}")
        return conn.execute(
            f"SELECT {', '.join(COLONNES)} FROM positions ORDER BY id").fetchall()
    finally:
        conn.close()


def _positif(valeur, nom: str):
    if not isinstance(valeur, (int, float)) or not math.isfinite(valeur) or valeur <= 0:
        raise ValueError(f"{nom} doit être un nombre strictement positif : {valeur!r}")
    return valeur


def _date(texte, nom: str) -> datetime:
    try:
        return datetime.fromisoformat(str(texte).strip())
    except ValueError:
        raise ValueError(f"{nom} illisible : {texte!r}") from None


def executions(p) -> list[dict]:
    """Exécutions d'une position : l'entrée, puis la sortie si elle est fermée."""
    direction = (p["direction"] or "").upper()
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"direction inconnue : {p['direction']!r}")
    statut = p["status"] or ""
    if statut != "OPEN" and not statut.startswith("CLOSED"):
        raise ValueError(f"statut inconnu : {p['status']!r}")
    entree, sortie = ("achat", "vente") if direction == "LONG" else ("vente", "achat")
    devise = devise_cotation(p["ticker"])
    quantite = _positif(p["quantity"], "quantité")
    stop = p["stop_loss"]
    lignes = [dict(
        horodatage=_date(p["entry_date"], "date d'entrée"), sens=entree, quantite=quantite,
        prix=_positif(p["entry_price"], "prix d'entrée"), devise=devise,
        ref_source=f"position-{p['id']}-entree",
        contexte={"bras": BRAS,
                  "stop_initial": stop if isinstance(stop, (int, float)) and stop > 0 else None})]
    if statut != "OPEN":
        lignes.append(dict(
            horodatage=_date(p["exit_date"], "date de sortie"), sens=sortie, quantite=quantite,
            prix=_positif(p["exit_price"], "prix de sortie"), devise=devise,
            ref_source=f"position-{p['id']}-sortie", contexte=None))
    return lignes


def _trade_actif(conn, ref_source: str) -> int | None:
    """Ligne active d'une exécution paper (elle-même ou sa dernière correction), sinon None."""
    ligne = conn.execute("SELECT id, statut FROM trades WHERE source = ? AND ref_source = ?",
                         (SOURCE, ref_source)).fetchone()
    while ligne is not None:
        suivante = conn.execute("SELECT id, statut FROM trades WHERE remplace_id = ?",
                                (ligne["id"],)).fetchone()
        if suivante is None:
            return ligne["id"] if ligne["statut"] == "valide" else None
        ligne = suivante
    return None


def synchroniser(conn, chemin_base: str, appliquer: bool = True, valider: bool = True) -> Rapport:
    """Inscrit au grand livre les positions paper qui n'y sont pas, annule celles marquées
    « boucle » depuis leur import. Rien n'est écrit s'il y a une erreur, ni à blanc
    (appliquer=False : la transaction est annulée, le rapport dit ce qui serait fait).
    valider=False : la transaction reste ouverte, l'appelant la valide avec d'autres écritures."""
    rapport = Rapport()
    a_ecrire, a_retirer, incertaines = [], [], set()
    for p in lire_positions(chemin_base):
        if p["boucle"]:
            rapport.boucles += 1
            a_retirer.append(p["id"])
            continue
        rapport.positions += 1
        try:
            a_ecrire.append((p, executions(p)))
        except ValueError as exc:
            rapport.erreurs.append((p["id"], str(exc)))
        if devise_incertaine(p["ticker"]):
            incertaines.add(p["ticker"].strip().upper())
    rapport.devises_incertaines = sorted(incertaines)
    if rapport.erreurs:
        return rapport
    try:
        compte_id = ecriture.compte(conn, COMPTE, "paper", DEVISE_COMPTE)
        for p, lignes in a_ecrire:
            instrument_id = ecriture.instrument(
                conn, p["ticker"], lignes[0]["devise"],
                classe=(p["asset_type"] or "action").lower())
            for ligne in lignes:
                cree = ecriture.enregistrer_trade(
                    conn, compte_id=compte_id, instrument_id=instrument_id,
                    source=SOURCE, **ligne)
                if cree is None:
                    rapport.deja_presents += 1
                else:
                    rapport.importes += 1
        for pos_id in a_retirer:
            for partie in ("entree", "sortie"):
                actif = _trade_actif(conn, f"position-{pos_id}-{partie}")
                if actif is not None:
                    ecriture.annuler_trade(conn, actif)
                    rapport.annules += 1
        if not appliquer:
            conn.rollback()
        elif valider:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport
