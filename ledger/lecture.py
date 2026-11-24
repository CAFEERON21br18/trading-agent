"""Lectures du grand livre : seules les lignes encore actives sont renvoyées."""
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Execution:
    """Un achat ou une vente, tel qu'il compte aujourd'hui."""
    id: int
    compte_id: int
    symbole: str
    horodatage: datetime
    sens: str
    quantite: Decimal
    prix: Decimal
    devise: str
    couts: Decimal = Decimal("0")
    stop_initial: Decimal | None = None
    bras: str | None = None


_REQUETE = """
SELECT t.id, t.compte_id, i.symbole, t.horodatage, t.sens, t.quantite, t.prix,
       t.devise, c.stop_initial, c.bras
FROM trades t
JOIN instruments i ON i.id = t.instrument_id
LEFT JOIN contexte_entree c ON c.trade_id = t.id
WHERE t.statut = 'valide'
  AND NOT EXISTS (SELECT 1 FROM trades r WHERE r.remplace_id = t.id)
  {filtre}
ORDER BY t.horodatage, t.id
"""


def executions_actives(conn: sqlite3.Connection,
                       compte_id: int | None = None) -> list[Execution]:
    """Exécutions ni corrigées ni annulées, de la plus ancienne à la plus récente."""
    filtre, params = ("AND t.compte_id = ?", (compte_id,)) if compte_id else ("", ())
    couts: dict[int, Decimal] = {}
    for ligne in conn.execute("SELECT trade_id, montant FROM couts"):
        couts[ligne["trade_id"]] = (
            couts.get(ligne["trade_id"], Decimal("0")) + Decimal(ligne["montant"]))
    return [
        Execution(
            id=l["id"], compte_id=l["compte_id"], symbole=l["symbole"],
            horodatage=datetime.fromisoformat(l["horodatage"]), sens=l["sens"],
            quantite=Decimal(l["quantite"]), prix=Decimal(l["prix"]),
            devise=l["devise"], couts=couts.get(l["id"], Decimal("0")),
            stop_initial=(None if l["stop_initial"] is None
                          else Decimal(l["stop_initial"])),
            bras=l["bras"],
        )
        for l in conn.execute(_REQUETE.format(filtre=filtre), params)
    ]


def taux_eurusd(conn: sqlite3.Connection) -> dict[date, Decimal]:
    """Taux EURUSD par jour. Pour un même jour, la dernière saisie l'emporte."""
    taux: dict[date, Decimal] = {}
    for l in conn.execute("SELECT jour, taux FROM change ORDER BY id"):
        taux[date.fromisoformat(l["jour"])] = Decimal(l["taux"])
    return taux


def valeurs_quotidiennes(conn: sqlite3.Connection,
                         compte_id: int) -> list[tuple[date, Decimal]]:
    """Valeur du compte par jour, triée. La dernière saisie du jour l'emporte."""
    valeurs: dict[date, Decimal] = {}
    for l in conn.execute(
        "SELECT jour, valeur FROM valeur_quotidienne WHERE compte_id = ?"
        " ORDER BY id", (compte_id,)):
        valeurs[date.fromisoformat(l["jour"])] = Decimal(l["valeur"])
    return sorted(valeurs.items())


@dataclass(frozen=True)
class Compte:
    id: int
    nom: str
    type: str
    devise: str


@dataclass(frozen=True)
class Mouvement:
    """Un dépôt, un retrait ou un dividende. Le montant est toujours positif."""
    id: int
    compte_id: int
    horodatage: datetime
    type: str
    montant: Decimal
    devise: str
    symbole: str | None = None


def _table_presente(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (table,)).fetchone() is not None


def comptes(conn: sqlite3.Connection) -> list[Compte]:
    """Les comptes du grand livre, dans l'ordre de leur création."""
    return [Compte(l["id"], l["nom"], l["type"], l["devise"])
            for l in conn.execute("SELECT id, nom, type, devise FROM comptes ORDER BY id")]


def mouvements(conn: sqlite3.Connection, compte_id: int) -> list[Mouvement]:
    """Mouvements d'argent du compte, du plus ancien au plus récent."""
    if not _table_presente(conn, "mouvements"):
        return []  # grand livre ouvert en lecture seule, créé avant la table
    return [
        Mouvement(id=l["id"], compte_id=l["compte_id"],
                  horodatage=datetime.fromisoformat(l["horodatage"]), type=l["type"],
                  montant=Decimal(l["montant"]), devise=l["devise"], symbole=l["symbole"])
        for l in conn.execute(
            "SELECT m.id, m.compte_id, m.horodatage, m.type, m.montant, m.devise, i.symbole"
            " FROM mouvements m LEFT JOIN instruments i ON i.id = m.instrument_id"
            " WHERE m.compte_id = ? ORDER BY m.horodatage, m.id", (compte_id,))
    ]


def references_presentes(conn: sqlite3.Connection, table: str, source: str) -> set[str]:
    """Références déjà inscrites pour une source, dans trades ou dans mouvements."""
    if table not in ("trades", "mouvements"):
        raise ValueError(f"table sans référence de source : {table!r}")
    if not _table_presente(conn, table):
        return set()
    return {l["ref_source"] for l in conn.execute(
        f"SELECT ref_source FROM {table} WHERE source = ?", (source,))}
