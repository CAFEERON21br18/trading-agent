"""Apparie les exécutions en trades clos, premier entré premier sorti."""
from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal

from .modeles import PositionOuverte, TradeClos


@dataclass
class _Lot:
    sens: str
    quantite: Decimal
    prix: Decimal
    cout_unitaire: Decimal
    execution: object


def reconstruire(executions) -> tuple[list[TradeClos], list[PositionOuverte]]:
    """Renvoie (trades clos, positions encore ouvertes).

    Une vente qui dépasse la position longue ouvre une position courte,
    ce qui couvre la vente à découvert sur CFD.
    """
    files: dict[tuple, deque[_Lot]] = defaultdict(deque)
    clos: list[TradeClos] = []
    for ex in sorted(executions, key=lambda e: (e.horodatage, e.id)):
        file = files[(ex.compte_id, ex.symbole)]
        restant = ex.quantite
        cout_u = ex.couts / ex.quantite
        while restant > 0 and file and file[0].sens != ex.sens:
            lot = file[0]
            q = min(restant, lot.quantite)
            clos.append(_clore(lot, ex, q, cout_u))
            lot.quantite -= q
            restant -= q
            if lot.quantite == 0:
                file.popleft()
        if restant > 0:
            file.append(_Lot(ex.sens, restant, ex.prix, cout_u, ex))
    ouvertes = [
        PositionOuverte(
            compte_id=lot.execution.compte_id, symbole=lot.execution.symbole,
            sens="long" if lot.sens == "achat" else "court",
            quantite=lot.quantite, prix_entree=lot.prix,
            ouvert_le=lot.execution.horodatage, devise=lot.execution.devise,
            couts=lot.cout_unitaire * lot.quantite)
        for file in files.values() for lot in file
    ]
    clos.sort(key=lambda t: t.clos_le)
    return clos, ouvertes


def _clore(lot: _Lot, sortie, q: Decimal, cout_sortie_u: Decimal) -> TradeClos:
    entree = lot.execution
    long = lot.sens == "achat"
    ecart = sortie.prix - lot.prix if long else lot.prix - sortie.prix
    stop = entree.stop_initial
    return TradeClos(
        compte_id=entree.compte_id, symbole=entree.symbole,
        sens="long" if long else "court", quantite=q,
        prix_entree=lot.prix, prix_sortie=sortie.prix,
        ouvert_le=entree.horodatage, clos_le=sortie.horodatage,
        devise=entree.devise, pnl_brut=ecart * q,
        couts=(lot.cout_unitaire + cout_sortie_u) * q,
        risque=None if stop is None else abs(lot.prix - stop) * q,
        bras=entree.bras,
    )
