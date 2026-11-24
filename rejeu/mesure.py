"""
rejeu/mesure.py — Mesures d'un compte du rejeu sur une période, calculées avec le paquet mesures.

Calcul pur sur des trades clos (mesures.TradeClos) et la valeur quotidienne du compte : ni agent,
ni base. Un trade appartient à l'année de sa CLÔTURE. La courbe d'une période part de la valeur
du compte la veille de son premier jour (le capital, pour la période entière).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import mesures
from rejeu import parametres as P


@dataclass(frozen=True)
class Bilan:
    """Mesures d'un compte sur une période. None : non calculable (jamais 0 à la place)."""
    debut: date
    fin: date
    trades: int
    resultat_net: float | None  # somme des résultats nets des trades clos
    resultat_brut: float | None
    frais: float | None
    esperance: float | None  # résultat net moyen par trade
    intervalle: tuple | None  # intervalle de confiance à 95 % de l'espérance (bootstrap)
    taux_reussite: float | None
    profit_factor: float | None
    part_frais: float | None  # frais / résultat brut, si le brut est positif
    valeur_debut: float | None
    valeur_fin: float | None
    rendement: float | None  # variation de la valeur du compte sur la période
    rendement_annualise: float | None
    drawdown_max: float | None  # négatif
    ratio: float | None  # rendement annualisé / |drawdown maximal|


def trades_de(trades: list, debut: date, fin: date) -> list:
    return [t for t in trades if debut <= t.clos_le.date() <= fin]


def serie_de(valeurs: list, debut: date, fin: date, capital) -> list:
    """Valeurs de la période, précédées de la valeur de la veille du premier jour."""
    avant = [v for j, v in valeurs if j < debut]
    depart = avant[-1] if avant else Decimal(capital)
    return [(debut - timedelta(days=1), depart)] + [(j, v) for j, v in valeurs if debut <= j <= fin]


def _somme(valeurs) -> float | None:
    valeurs = list(valeurs)
    return float(sum(valeurs, Decimal(0))) if valeurs else None


def bilan(trades: list, valeurs: list, debut: date, fin: date, capital) -> Bilan:
    """Toutes les mesures du compte entre debut et fin compris."""
    clos = trades_de(trades, debut, fin)
    serie = serie_de(valeurs, debut, fin, capital)
    n = len(clos)
    drawdown = mesures.drawdown_max(serie, n).valeur
    annualise = mesures.rendement_annualise(serie, n).valeur
    ratio = annualise / abs(drawdown) if annualise is not None and drawdown else None
    return Bilan(
        debut=debut, fin=fin, trades=n,
        resultat_net=mesures.resultat_net(clos).valeur,
        resultat_brut=_somme(t.pnl_brut for t in clos), frais=_somme(t.couts for t in clos),
        esperance=mesures.esperance_nette(clos).valeur,
        intervalle=mesures.intervalle_esperance(clos, P.TIRAGES, P.GRAINE, P.CONFIANCE),
        taux_reussite=mesures.taux_reussite(clos).valeur, profit_factor=mesures.profit_factor(clos).valeur,
        part_frais=mesures.part_des_couts(clos).valeur,
        valeur_debut=float(serie[0][1]), valeur_fin=float(serie[-1][1]),
        rendement=mesures.rendement(serie, n).valeur, rendement_annualise=annualise,
        drawdown_max=drawdown, ratio=ratio)


def ecart(valeurs: list, reference: list, debut: date, fin: date, capital) -> float | None:
    """Rendement du compte moins celui de la référence, sur les jours communs de la période."""
    return mesures.ecart_au_benchmark(serie_de(valeurs, debut, fin, capital),
                                      serie_de(reference, debut, fin, capital), 0).valeur


def annee(numero: int, dernier_jour: date | None = None) -> tuple[date, date]:
    """Bornes d'une année civile (la dernière, partielle, s'arrête à `dernier_jour`)."""
    fin = date(numero, 12, 31)
    return date(numero, 1, 1), min(fin, dernier_jour) if dernier_jour else fin
