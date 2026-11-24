"""Bascule euro/dollar avec le taux EURUSD du jour (dollars pour un euro)."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from .modeles import TradeClos

DEVISES = ("EUR", "USD")
TOLERANCE_JOURS = 7  # week-ends et jours fériés : on reprend le dernier taux connu


class TauxManquant(LookupError):
    """Aucun taux stocké assez proche du jour demandé."""


def taux_du_jour(taux: dict[date, Decimal], jour: date) -> Decimal:
    """Taux du jour, sinon le dernier taux connu dans les 7 jours précédents."""
    for recul in range(TOLERANCE_JOURS + 1):
        trouve = taux.get(jour - timedelta(days=recul))
        if trouve is not None:
            return trouve
    raise TauxManquant(f"aucun taux EURUSD entre {jour} et {TOLERANCE_JOURS} jours avant")


def convertir(montant: Decimal, de: str, vers: str, jour: date,
              taux: dict[date, Decimal]) -> Decimal:
    """Convertit un montant entre EUR et USD au taux stocké."""
    if de == vers:
        return montant
    if de not in DEVISES or vers not in DEVISES:
        raise ValueError(f"conversion non prise en charge : {de} vers {vers}")
    t = taux_du_jour(taux, jour)
    return montant * t if de == "EUR" else montant / t


def en_devise(trades: list[TradeClos], devise: str,
              taux: dict[date, Decimal]) -> list[TradeClos]:
    """Exprime le résultat, les coûts et le risque de chaque trade dans la devise voulue.

    Le taux retenu est celui du jour de clôture. Les prix restent dans la
    devise de cotation ; seul le champ devise et les montants changent.
    """
    convertis = []
    for t in trades:
        if t.devise == devise:
            convertis.append(t)
            continue
        jour = t.clos_le.date()
        convertis.append(replace(
            t, devise=devise,
            pnl_brut=convertir(t.pnl_brut, t.devise, devise, jour, taux),
            couts=convertir(t.couts, t.devise, devise, jour, taux),
            risque=(None if t.risque is None
                    else convertir(t.risque, t.devise, devise, jour, taux)),
        ))
    return convertis
