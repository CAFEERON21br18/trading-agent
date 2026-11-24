"""Mesures calculées sur la valeur quotidienne d'un compte.

La série doit être un indice de performance : les dépôts et retraits
doivent déjà être neutralisés, sinon un dépôt passe pour un gain.
"""
import math
from datetime import date
from decimal import Decimal

from .modeles import Mesure, mesure

JOURS_PAR_AN = 252
Serie = list[tuple[date, Decimal]]


def _bornes(serie: Serie):
    return (serie[0][0], serie[-1][0]) if serie else (None, None)


def _variations(serie: Serie) -> list[float]:
    valeurs = [float(v) for _, v in serie]
    return [b / a - 1 for a, b in zip(valeurs, valeurs[1:]) if a > 0]


def rendement(serie: Serie, n_trades: int) -> Mesure:
    """Variation entre la première et la dernière valeur."""
    valeur = None
    if len(serie) >= 2 and serie[0][1] > 0:
        valeur = serie[-1][1] / serie[0][1] - 1
    return mesure("rendement", valeur, n_trades, *_bornes(serie))


def drawdown_max(serie: Serie, n_trades: int) -> Mesure:
    """Plus forte baisse depuis un sommet, en valeur négative."""
    valeur = None
    if len(serie) >= 2:
        sommet, pire = serie[0][1], Decimal("0")
        for _, v in serie:
            sommet = max(sommet, v)
            if sommet > 0:
                pire = min(pire, v / sommet - 1)
        valeur = pire
    return mesure("drawdown max", valeur, n_trades, *_bornes(serie))


def sharpe(serie: Serie, n_trades: int) -> Mesure:
    """Rendement quotidien moyen sur son écart-type, annualisé, taux sans risque nul."""
    var = _variations(serie)
    valeur = None
    if len(var) >= 2:
        moyenne = sum(var) / len(var)
        ecart = math.sqrt(sum((x - moyenne) ** 2 for x in var) / (len(var) - 1))
        if ecart > 0:
            valeur = moyenne / ecart * math.sqrt(JOURS_PAR_AN)
    return mesure("Sharpe", valeur, n_trades, *_bornes(serie))


def sortino(serie: Serie, n_trades: int) -> Mesure:
    """Comme le Sharpe, mais seules les baisses comptent dans le risque."""
    var = _variations(serie)
    valeur = None
    if len(var) >= 2:
        moyenne = sum(var) / len(var)
        baisse = math.sqrt(sum(min(x, 0.0) ** 2 for x in var) / len(var))
        if baisse > 0:
            valeur = moyenne / baisse * math.sqrt(JOURS_PAR_AN)
    return mesure("Sortino", valeur, n_trades, *_bornes(serie))


def ecart_au_benchmark(serie: Serie, benchmark: Serie, n_trades: int) -> Mesure:
    """Rendement du compte moins celui du benchmark, sur les jours communs."""
    jours = {j for j, _ in serie} & {j for j, _ in benchmark}
    a = [(j, v) for j, v in serie if j in jours]
    b = [(j, v) for j, v in benchmark if j in jours]
    valeur = None
    if len(a) >= 2 and a[0][1] > 0 and b[0][1] > 0:
        valeur = (a[-1][1] / a[0][1]) - (b[-1][1] / b[0][1])
    return mesure("écart au benchmark", valeur, n_trades, *_bornes(a))


def levier(notionnel_total: Decimal, capital: Decimal) -> float | None:
    """Exposition totale divisée par le capital. 1 signifie sans levier."""
    return float(notionnel_total / capital) if capital > 0 else None
