"""Mesures sur les mouvements d'argent d'un compte : dépôts, retraits, dividendes.

Un mouvement est un objet qui porte type, montant, devise et horodatage (ledger.Mouvement).
Ce sont des sommes de faits, pas des estimations : le seuil de 100 trades ne s'y applique
pas. Une somme est donc décidable dès qu'il y a un mouvement ; sans mouvement, elle est
« non calculable » (None, jamais 0).
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal

from .conversion import convertir
from .modeles import Mesure


def mouvements_en_devise(mouvements: list, devise: str,
                         taux: dict[date, Decimal]) -> list:
    """Exprime chaque montant dans la devise voulue, au taux du jour du mouvement."""
    return [
        m if m.devise == devise else replace(
            m, devise=devise,
            montant=convertir(m.montant, m.devise, devise, m.horodatage.date(), taux))
        for m in mouvements
    ]


def _somme(nom: str, mouvements: list, signes: dict[str, int]) -> Mesure:
    retenus = [m for m in mouvements if m.type in signes]
    devises = {m.devise for m in retenus}
    if len(devises) > 1:
        raise ValueError(f"devises mélangées : {sorted(devises)} ; convertir avant")
    if not retenus:
        return Mesure(nom, None, 0, None, None, False, "non calculable")
    total = sum((signes[m.type] * m.montant for m in retenus), Decimal("0"))
    jours = [m.horodatage.date() for m in retenus]
    return Mesure(nom, float(total), len(retenus), min(jours), max(jours), True)


def dividendes(mouvements: list) -> Mesure:
    """Somme des dividendes reçus. n compte les dividendes."""
    return _somme("dividendes", mouvements, {"dividende": 1})


def apports_nets(mouvements: list) -> Mesure:
    """Dépôts moins retraits. n compte les dépôts et les retraits."""
    return _somme("apports nets", mouvements, {"depot": 1, "retrait": -1})
