"""Espérance nette par trade et son intervalle de confiance par rééchantillonnage (bootstrap).

Calcul pur, sans accès à la base. L'intervalle est celui des percentiles : on tire `tirages`
échantillons de même taille, avec remise, parmi les résultats nets des trades ; l'intervalle à
95 % va du percentile 2,5 au percentile 97,5 des moyennes obtenues. La graine fixe rend le
résultat reproductible. numpy n'est chargé qu'à l'appel.
"""
from decimal import Decimal

from .modeles import Mesure, TradeClos, mesure
from .resultats import _periode, _une_devise


def esperance_nette(trades: list[TradeClos]) -> Mesure:
    """Résultat net moyen par trade, dans la devise des trades."""
    _une_devise(trades)
    valeur = None
    if trades:
        valeur = sum((t.pnl_net for t in trades), Decimal("0")) / len(trades)
    return mesure("espérance nette", valeur, len(trades), *_periode(trades))


def intervalle_bootstrap(valeurs: list, tirages: int = 10_000, graine: int = 0,
                         confiance: float = 0.95) -> tuple[float, float] | None:
    """Intervalle de confiance de la moyenne de `valeurs`. None avec moins de 2 valeurs."""
    if len(valeurs) < 2:
        return None
    import numpy as np
    donnees = np.array([float(v) for v in valeurs])
    alea = np.random.default_rng(graine)
    moyennes = np.empty(tirages)
    lot = max(1, min(tirages, 2_000_000 // len(donnees)))  # borne la mémoire d'un lot de tirages
    for debut in range(0, tirages, lot):
        n = min(lot, tirages - debut)
        indices = alea.integers(0, len(donnees), size=(n, len(donnees)))
        moyennes[debut:debut + n] = donnees[indices].mean(axis=1)
    marge = (1 - confiance) / 2 * 100
    bas, haut = np.percentile(moyennes, [marge, 100 - marge])
    return float(bas), float(haut)


def intervalle_esperance(trades: list[TradeClos], tirages: int = 10_000, graine: int = 0,
                         confiance: float = 0.95) -> tuple[float, float] | None:
    """Intervalle de confiance de l'espérance nette par trade."""
    _une_devise(trades)
    return intervalle_bootstrap([t.pnl_net for t in trades], tirages, graine, confiance)
