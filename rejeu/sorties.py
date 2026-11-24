"""
rejeu/sorties.py — Sortie d'une position sur une barre quotidienne (stop et objectif).

Calcul pur, sans agent ni base. Le stop et l'objectif sont ceux que l'agent a écrits à
l'ouverture de la position (stop_loss, target_1 : le moniteur de l'agent sort au premier
objectif atteint). Sur une barre, on ne sait pas lequel a été touché en premier :
- si le stop et l'objectif sont tous deux touchés le même jour, le STOP est pris ;
- une ouverture au-delà du stop exécute à l'ouverture (le stop n'a pas pu être servi à son prix) ;
- une ouverture au-delà de l'objectif exécute AU PRIX DE L'OBJECTIF, pas mieux : l'écart
  favorable n'est pas compté (choix qui désavantage la stratégie).
Le haut et le bas retenus encadrent l'ouverture et la clôture, même si la source donne une
barre légèrement incohérente.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Sortie:
    prix: float
    statut: str  # CLOSED_SL ou CLOSED_TP, comme le moniteur de l'agent
    raison: str


def tester(direction: str, stop: float, objectif: float, ouverture: float, haut: float, bas: float,
           cloture: float, entree_ce_jour: bool = False) -> Sortie | None:
    """Sortie de la position sur cette barre, ou None si ni le stop ni l'objectif n'est touché.

    entree_ce_jour : la position vient d'être ouverte à l'ouverture de cette barre ; l'ouverture
    n'est alors pas un écart (c'est son prix d'entrée), seuls le haut et le bas comptent.
    """
    haut, bas = max(ouverture, haut, bas, cloture), min(ouverture, haut, bas, cloture)
    if direction == "LONG":
        if not entree_ce_jour and ouverture <= stop:
            return Sortie(ouverture, "CLOSED_SL", f"Stop-loss franchi à l'ouverture ({ouverture:.4f} ≤ {stop:.4f})")
        if bas <= stop:
            return Sortie(stop, "CLOSED_SL", f"Stop-loss touché ({bas:.4f} ≤ {stop:.4f})")
        if haut >= objectif:
            return Sortie(objectif, "CLOSED_TP", f"Target 1 atteint ({haut:.4f} ≥ {objectif:.4f})")
        return None
    if direction == "SHORT":
        if not entree_ce_jour and ouverture >= stop:
            return Sortie(ouverture, "CLOSED_SL", f"Stop-loss franchi à l'ouverture ({ouverture:.4f} ≥ {stop:.4f})")
        if haut >= stop:
            return Sortie(stop, "CLOSED_SL", f"Stop-loss touché ({haut:.4f} ≥ {stop:.4f})")
        if bas <= objectif:
            return Sortie(objectif, "CLOSED_TP", f"Target 1 atteint ({bas:.4f} ≤ {objectif:.4f})")
        return None
    raise ValueError(f"direction inconnue : {direction!r}")
