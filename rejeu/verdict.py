"""
rejeu/verdict.py — Le verdict du rejeu, en appliquant mot pour mot le critère du registre (§10).

Verdict « utile » si les trois conditions sont vraies, sinon « sans avantage » :
 1. espérance nette par trade positive, avec un intervalle de confiance à 95 % entièrement
    au-dessus de zéro (bootstrap, 10 000 tirages, graine fixe), sur l'ensemble de la période ;
 2. rendement annualisé divisé par le drawdown maximal supérieur à celui d'« acheter et garder »
    le même univers, mêmes frais, même capital, sur l'ensemble de la période ;
 3. stabilité : espérance nette positive dans au moins 4 des 8 années, et résultat total encore
    positif une fois retirée la meilleure année.
Moins de 100 trades clos sur la période : « non décidable ».
La consigne définit deux références « acheter et garder » : pour la condition 2, la stratégie
doit dépasser LES DEUX. Calcul pur : aucune base, aucun agent.
"""

from dataclasses import dataclass

from rejeu import parametres as P
from rejeu.mesure import Bilan

UTILE, SANS_AVANTAGE, NON_DECIDABLE = "utile", "sans avantage", "non décidable"
ANNEES_REQUISES = 4


@dataclass(frozen=True)
class Condition:
    numero: int
    titre: str
    vraie: bool
    constat: str  # la condition, chiffres à l'appui


def _eur(v) -> str:
    return "non calculable" if v is None else f"{v:+.2f} €".replace(".", ",").replace("-", "−")


def _ratio(v) -> str:
    return "non calculable" if v is None else f"{v:+.3f}".replace(".", ",").replace("-", "−")


def condition_1(periode: Bilan) -> Condition:
    bas, haut = periode.intervalle or (None, None)
    vraie = bool(periode.esperance is not None and periode.esperance > 0 and bas is not None and bas > 0)
    return Condition(1, "Espérance nette par trade positive, intervalle à 95 % entièrement au-dessus de zéro", vraie,
                     f"espérance nette {_eur(periode.esperance)} par trade sur {periode.trades} trades ; "
                     f"intervalle à 95 % : de {_eur(bas)} à {_eur(haut)}")


def condition_2(periode: Bilan, ref_annuelle: Bilan, ref_periode: Bilan) -> Condition:
    references = [ref_annuelle.ratio, ref_periode.ratio]
    vraie = bool(periode.ratio is not None and all(r is not None and periode.ratio > r for r in references))
    return Condition(2, "Rendement annualisé / drawdown maximal supérieur à celui d'« acheter et garder »", vraie,
                     f"stratégie {_ratio(periode.ratio)} ; référence rachetée chaque année {_ratio(ref_annuelle.ratio)} ; "
                     f"référence gardée sur la période {_ratio(ref_periode.ratio)} (il faut dépasser les deux)")


def condition_3(annees: dict[int, Bilan]) -> Condition:
    positives = [a for a, b in annees.items() if b.esperance is not None and b.esperance > 0]
    nets = {a: b.resultat_net or 0.0 for a, b in annees.items()}
    meilleure = max(nets, key=nets.get)
    reste = sum(nets.values()) - nets[meilleure]
    vraie = len(positives) >= ANNEES_REQUISES and reste > 0
    return Condition(3, "Stabilité : espérance positive dans au moins 4 des 8 années, total positif sans la meilleure année",
                     vraie, f"espérance nette positive dans {len(positives)} des {len(annees)} années "
                     f"({', '.join(str(a) for a in positives) or 'aucune'}) ; résultat total sans la meilleure année "
                     f"({meilleure}) : {_eur(reste)}")


def rendre(periode: Bilan, ref_annuelle: Bilan, ref_periode: Bilan, annees: dict[int, Bilan]) -> tuple[str, list[Condition]]:
    """(verdict, les trois conditions). Les conditions sont données même si le verdict est « non décidable »."""
    conditions = [condition_1(periode), condition_2(periode, ref_annuelle, ref_periode), condition_3(annees)]
    if periode.trades < P.MIN_TRADES:
        return NON_DECIDABLE, conditions
    return (UTILE if all(c.vraie for c in conditions) else SANS_AVANTAGE), conditions
