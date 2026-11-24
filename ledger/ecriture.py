"""Écritures dans le grand livre. On ajoute des lignes, on n'en modifie jamais."""
import sqlite3
from datetime import date, datetime

from ._valeurs import EcritureInvalide, _iso, _maintenant, _positif

TYPES_MOUVEMENT = ("depot", "retrait", "dividende")


def compte(conn: sqlite3.Connection, nom: str, type_: str, devise: str) -> int:
    """Renvoie l'identifiant du compte, en le créant s'il n'existe pas."""
    ligne = conn.execute("SELECT id FROM comptes WHERE nom = ?", (nom,)).fetchone()
    if ligne:
        return ligne["id"]
    cur = conn.execute(
        "INSERT INTO comptes (nom, type, devise, cree_le) VALUES (?, ?, ?, ?)",
        (nom, type_, devise.upper(), _maintenant()),
    )
    return cur.lastrowid


def instrument(conn, symbole: str, devise: str, nom: str | None = None,
               classe: str = "action") -> int:
    """Renvoie l'identifiant de l'instrument, en le créant s'il n'existe pas."""
    symbole = symbole.strip().upper()
    ligne = conn.execute(
        "SELECT id FROM instruments WHERE symbole = ?", (symbole,)
    ).fetchone()
    if ligne:
        return ligne["id"]
    cur = conn.execute(
        "INSERT INTO instruments (symbole, nom, classe, devise) VALUES (?, ?, ?, ?)",
        (symbole, nom, classe, devise.upper()),
    )
    return cur.lastrowid


def enregistrer_trade(conn, *, compte_id: int, instrument_id: int,
                      horodatage: datetime, sens: str, quantite, prix,
                      devise: str, source: str, ref_source: str,
                      taux_change=None, couts=(), contexte: dict | None = None,
                      statut: str = "valide", remplace_id: int | None = None):
    """Ajoute une exécution. Renvoie son id, ou None si elle est déjà présente.

    couts : suite de (type, montant), dans la devise du trade.
    contexte : dict facultatif avec bras, stop_initial, horizon, note.
    """
    if sens not in ("achat", "vente"):
        raise EcritureInvalide(f"sens inconnu : {sens!r}")
    deja = conn.execute(
        "SELECT 1 FROM trades WHERE source = ? AND ref_source = ?",
        (source, ref_source),
    ).fetchone()
    if deja:
        return None
    cur = conn.execute(
        "INSERT INTO trades (compte_id, instrument_id, horodatage, sens, quantite,"
        " prix, devise, taux_change, source, ref_source, statut, remplace_id,"
        " saisi_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (compte_id, instrument_id, _iso(horodatage), sens,
         _positif(quantite, "quantité"), _positif(prix, "prix"), devise.upper(),
         None if taux_change is None else _positif(taux_change, "taux de change"),
         source, ref_source, statut, remplace_id, _maintenant()),
    )
    trade_id = cur.lastrowid
    for type_, montant in couts:
        conn.execute(
            "INSERT INTO couts (trade_id, type, montant, devise) VALUES (?, ?, ?, ?)",
            (trade_id, type_, _positif(montant, "coût"), devise.upper()),
        )
    if contexte:
        stop = contexte.get("stop_initial")
        conn.execute(
            "INSERT INTO contexte_entree (trade_id, bras, stop_initial, horizon,"
            " note) VALUES (?, ?, ?, ?, ?)",
            (trade_id, contexte.get("bras"),
             None if stop is None else _positif(stop, "stop initial"),
             contexte.get("horizon"), contexte.get("note")),
        )
    return trade_id


def _ligne_active(conn, trade_id: int) -> sqlite3.Row:
    ligne = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if ligne is None:
        raise EcritureInvalide(f"trade {trade_id} introuvable")
    remplace = conn.execute(
        "SELECT 1 FROM trades WHERE remplace_id = ?", (trade_id,)
    ).fetchone()
    if remplace or ligne["statut"] != "valide":
        raise EcritureInvalide(f"trade {trade_id} déjà corrigé ou annulé")
    return ligne


def corriger_trade(conn, trade_id: int, *, couts=None, contexte=None,
                   **changements) -> int:
    """Corrige un trade par une nouvelle ligne qui remplace l'ancienne.

    changements : horodatage, sens, quantite, prix, devise, taux_change.
    Sans couts ni contexte fournis, ceux de l'ancienne ligne sont repris.
    """
    ancien = _ligne_active(conn, trade_id)
    inconnus = set(changements) - {
        "horodatage", "sens", "quantite", "prix", "devise", "taux_change"}
    if inconnus:
        raise EcritureInvalide(f"champs non corrigeables : {sorted(inconnus)}")
    if couts is None:
        couts = [(c["type"], c["montant"]) for c in conn.execute(
            "SELECT type, montant FROM couts WHERE trade_id = ?", (trade_id,))]
    if contexte is None:
        ctx = conn.execute(
            "SELECT bras, stop_initial, horizon, note FROM contexte_entree"
            " WHERE trade_id = ?", (trade_id,)).fetchone()
        contexte = dict(ctx) if ctx else None
    valeurs = {
        "horodatage": datetime.fromisoformat(ancien["horodatage"]),
        "sens": ancien["sens"], "quantite": ancien["quantite"],
        "prix": ancien["prix"], "devise": ancien["devise"],
        "taux_change": ancien["taux_change"],
    }
    valeurs.update(changements)
    return enregistrer_trade(
        conn, compte_id=ancien["compte_id"], instrument_id=ancien["instrument_id"],
        source=ancien["source"], ref_source=f"{ancien['ref_source']}#corr{trade_id}",
        couts=couts, contexte=contexte, remplace_id=trade_id, **valeurs)


def annuler_trade(conn, trade_id: int) -> int:
    """Annule un trade par une ligne d'annulation. L'ancienne ligne reste lisible."""
    ancien = _ligne_active(conn, trade_id)
    return enregistrer_trade(
        conn, compte_id=ancien["compte_id"], instrument_id=ancien["instrument_id"],
        horodatage=datetime.fromisoformat(ancien["horodatage"]),
        sens=ancien["sens"], quantite=ancien["quantite"], prix=ancien["prix"],
        devise=ancien["devise"], source=ancien["source"],
        ref_source=f"{ancien['ref_source']}#annul{trade_id}",
        statut="annulation", remplace_id=trade_id)


def enregistrer_taux(conn, jour: date, taux, source: str) -> int:
    """Stocke le taux EURUSD du jour (dollars pour un euro)."""
    cur = conn.execute(
        "INSERT INTO change (jour, paire, taux, source, saisi_le)"
        " VALUES (?, 'EURUSD', ?, ?, ?)",
        (jour.isoformat(), _positif(taux, "taux"), source, _maintenant()),
    )
    return cur.lastrowid


def enregistrer_valeur(conn, compte_id: int, jour: date, valeur, devise: str) -> int:
    """Stocke la valeur du compte en fin de journée."""
    cur = conn.execute(
        "INSERT INTO valeur_quotidienne (compte_id, jour, valeur, devise, saisi_le)"
        " VALUES (?, ?, ?, ?, ?)",
        (compte_id, jour.isoformat(), _positif(valeur, "valeur"), devise.upper(),
         _maintenant()),
    )
    return cur.lastrowid


def enregistrer_mouvement(conn, *, compte_id: int, horodatage: datetime, type_: str,
                          montant, devise: str, source: str, ref_source: str,
                          instrument_id: int | None = None):
    """Ajoute un dépôt, un retrait ou un dividende. Renvoie son id, ou None s'il est déjà présent.

    montant : toujours positif, c'est le type qui donne le sens.
    instrument_id : facultatif, le titre qui verse un dividende.
    """
    if type_ not in TYPES_MOUVEMENT:
        raise EcritureInvalide(f"type de mouvement inconnu : {type_!r}")
    deja = conn.execute(
        "SELECT 1 FROM mouvements WHERE source = ? AND ref_source = ?",
        (source, ref_source),
    ).fetchone()
    if deja:
        return None
    cur = conn.execute(
        "INSERT INTO mouvements (compte_id, horodatage, type, montant, devise,"
        " instrument_id, source, ref_source, saisi_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (compte_id, _iso(horodatage), type_, _positif(montant, "montant"),
         devise.upper(), instrument_id, source, ref_source, _maintenant()),
    )
    return cur.lastrowid
