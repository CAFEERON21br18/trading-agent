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
