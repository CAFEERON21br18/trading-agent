"""
rejeu/frais.py — Frais d'un ordre selon le profil (rejeu/parametres.py : PROFILS).

Calcul pur. Montants en Decimal, dans la devise du rejeu. Chaque frais porte le type que le
grand livre connaît : commission, spread, financement.
- « Revolut » : une commission fixe par ordre.
- « CFD » : un écart à chaque côté, en part du montant de l'ordre, selon le type du titre ; à la
  sortie, un financement par nuit sur le montant de la position à l'entrée.
L'agent, lui, ne compte aucun frais : ses règles voient des résultats bruts, comme en production.
"""

from datetime import date
from decimal import Decimal

from rejeu import parametres as P

D = Decimal


def decimal(valeur) -> Decimal:
    return valeur if isinstance(valeur, Decimal) else D(repr(float(valeur)))


def type_titre(ticker: str) -> str:
    """Type du titre, par la règle de l'agent (agents/paper_trader/executor.py : _detecter_type)."""
    from agents.paper_trader.executor import _detecter_type
    return _detecter_type(ticker)


def _ecart(profil: str, ticker: str, montant: Decimal) -> Decimal:
    taux = P.PROFILS[profil]["ecart"].get(type_titre(ticker), D(0)) if P.PROFILS[profil]["ecart"] else D(0)
    return taux * montant


def nuits(entree: date, sortie: date) -> int:
    """Nuits passées en position : jours calendaires entre le jour d'entrée et le jour de sortie."""
    return max(0, (sortie - entree).days)


def financement(profil: str, montant_entree, entree: date, jusqu_a: date) -> Decimal:
    """Financement dû pour les nuits écoulées, sur le montant de la position à l'entrée."""
    return P.PROFILS[profil]["financement_par_nuit"] * decimal(montant_entree) * nuits(entree, jusqu_a)


def _liste(*couples) -> list[tuple[str, Decimal]]:
    return [(type_, montant) for type_, montant in couples if montant > 0]


def entree(profil: str, ticker: str, quantite, prix) -> list[tuple[str, Decimal]]:
    """Frais de l'ordre d'entrée : suite de (type, montant)."""
    montant = decimal(quantite) * decimal(prix)
    return _liste(("commission", P.PROFILS[profil]["par_ordre"]), ("spread", _ecart(profil, ticker, montant)))


def sortie(profil: str, ticker: str, quantite, prix, prix_entree, jour_entree: date,
           jour_sortie: date) -> list[tuple[str, Decimal]]:
    """Frais de l'ordre de sortie, financement des nuits compris."""
    montant = decimal(quantite) * decimal(prix)
    montant_entree = decimal(quantite) * decimal(prix_entree)
    return _liste(("commission", P.PROFILS[profil]["par_ordre"]), ("spread", _ecart(profil, ticker, montant)),
                  ("financement", financement(profil, montant_entree, jour_entree, jour_sortie)))


def total(frais: list[tuple[str, Decimal]]) -> Decimal:
    return sum((montant for _, montant in frais), D(0))
