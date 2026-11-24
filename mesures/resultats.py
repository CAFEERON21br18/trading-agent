"""Mesures calculées sur les trades clos, tous exprimés dans une même devise."""
from decimal import Decimal

from .modeles import Mesure, TradeClos, mesure


def _periode(trades: list[TradeClos]):
    if not trades:
        return None, None
    return (min(t.ouvert_le for t in trades).date(),
            max(t.clos_le for t in trades).date())


def _une_devise(trades: list[TradeClos]) -> None:
    devises = {t.devise for t in trades}
    if len(devises) > 1:
        raise ValueError(f"devises mélangées : {sorted(devises)} ; convertir avant")


def resultat_net(trades: list[TradeClos]) -> Mesure:
    """Somme des résultats après coûts."""
    _une_devise(trades)
    valeur = sum((t.pnl_net for t in trades), Decimal("0")) if trades else None
    return mesure("résultat net", valeur, len(trades), *_periode(trades))


def taux_reussite(trades: list[TradeClos]) -> Mesure:
    """Part des trades dont le résultat net est positif."""
    valeur = None
    if trades:
        valeur = sum(1 for t in trades if t.pnl_net > 0) / len(trades)
    return mesure("taux de réussite", valeur, len(trades), *_periode(trades))


def payoff(trades: list[TradeClos]) -> Mesure:
    """Gain moyen divisé par la perte moyenne."""
    _une_devise(trades)
    gains = [t.pnl_net for t in trades if t.pnl_net > 0]
    pertes = [-t.pnl_net for t in trades if t.pnl_net < 0]
    valeur = None
    if gains and pertes:
        valeur = (sum(gains) / len(gains)) / (sum(pertes) / len(pertes))
    return mesure("payoff", valeur, len(trades), *_periode(trades))


def profit_factor(trades: list[TradeClos]) -> Mesure:
    """Somme des gains divisée par la somme des pertes."""
    _une_devise(trades)
    gains = sum((t.pnl_net for t in trades if t.pnl_net > 0), Decimal("0"))
    pertes = sum((-t.pnl_net for t in trades if t.pnl_net < 0), Decimal("0"))
    valeur = gains / pertes if pertes > 0 else None
    return mesure("profit factor", valeur, len(trades), *_periode(trades))


def esperance_r(trades: list[TradeClos]) -> Mesure:
    """Résultat moyen par trade, en multiples du risque initial.

    Seuls les trades dont le stop initial est connu comptent, et n les compte.
    """
    avec_risque = [t for t in trades if t.r is not None]
    valeur = None
    if avec_risque:
        valeur = sum(t.r for t in avec_risque) / len(avec_risque)
    return mesure("espérance en R", valeur, len(avec_risque), *_periode(avec_risque))


def part_des_couts(trades: list[TradeClos]) -> Mesure:
    """Coûts totaux divisés par le résultat brut total.

    Non calculable quand le résultat brut est nul ou négatif : le ratio
    n'aurait pas de sens.
    """
    _une_devise(trades)
    brut = sum((t.pnl_brut for t in trades), Decimal("0"))
    couts = sum((t.couts for t in trades), Decimal("0"))
    valeur = couts / brut if brut > 0 else None
    return mesure("part des coûts", valeur, len(trades), *_periode(trades))


def tableau(trades: list[TradeClos]) -> list[Mesure]:
    """Toutes les mesures sur trades, dans l'ordre d'affichage."""
    return [f(trades) for f in (resultat_net, taux_reussite, payoff,
                                profit_factor, esperance_r, part_des_couts)]
