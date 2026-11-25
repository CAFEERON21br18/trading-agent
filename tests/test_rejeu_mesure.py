"""
tests/test_rejeu_mesure.py — Mesures et verdict du rejeu (mesures/bootstrap.py, mesures/courbe.py,
rejeu/mesure.py, rejeu/verdict.py).

1. espérance nette et intervalle par bootstrap : reproductible à graine fixe, encadre la moyenne ;
2. rendement annualisé ; bilan d'une période calculé à la main (trades de l'année de leur
   clôture, courbe qui part de la veille) ;
3. verdict : « utile » si les trois conditions sont vraies, « sans avantage » dès qu'une est
   fausse, « non décidable » sous 100 trades ; la condition 2 exige de dépasser les deux
   références ; la condition 3 retire la meilleure année.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_mesure -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import mesures
from rejeu import mesure, verdict
from rejeu import parametres as P


def trade(net: str, clos: date, frais: str = "2") -> mesures.TradeClos:
    quand = datetime(clos.year, clos.month, clos.day, 12, tzinfo=timezone.utc)
    return mesures.TradeClos(1, "AAA", "long", D("1"), D("100"), D("100"), quand, quand, "EUR",
                             D(net) + D(frais), D(frais))


class TestBootstrap(unittest.TestCase):
    def test_intervalle_reproductible_qui_encadre_la_moyenne(self):
        valeurs = [D("3"), D("-2"), D("5"), D("1"), D("-1"), D("4")] * 30
        a = mesures.intervalle_bootstrap(valeurs, 10_000, 20261124)
        self.assertEqual(a, mesures.intervalle_bootstrap(valeurs, 10_000, 20261124))  # graine fixe
        self.assertNotEqual(a, mesures.intervalle_bootstrap(valeurs, 10_000, 1))
        moyenne = float(sum(valeurs)) / len(valeurs)
        self.assertTrue(a[0] < moyenne < a[1])
        self.assertTrue(1.2 < a[0] < 1.4 and 1.9 < a[1] < 2.2, a)  # moyenne 1,667, écart-type 2,6, n = 180
        self.assertIsNone(mesures.intervalle_bootstrap([D("1")]))
        self.assertEqual(mesures.intervalle_bootstrap([D("2")] * 50, 1000, 3), (2.0, 2.0))

    def test_esperance_nette(self):
        trades = [trade("3", date(2018, 3, 1)), trade("-1", date(2018, 4, 1))]
        m = mesures.esperance_nette(trades)
        self.assertEqual((m.nom, m.valeur, m.n, m.decidable), ("espérance nette", 1.0, 2, False))
        self.assertIsNone(mesures.esperance_nette([]).valeur)
        bas, haut = mesures.intervalle_esperance(trades * 60, 2000, 7)
        self.assertTrue(bas < 1.0 < haut)

    def test_rendement_annualise(self):
        serie = [(date(2018, 1, 1), D("1000")), (date(2020, 1, 1), D("1210"))]
        self.assertAlmostEqual(mesures.rendement_annualise(serie, 5).valeur, 0.10, places=3)  # +21 % en 2 ans
        self.assertAlmostEqual(mesures.rendement_annualise([(date(2018, 1, 1), D("1000")), (date(2019, 1, 1), D("900"))], 5).valeur,
                               -0.10, places=3)
        self.assertEqual(mesures.rendement_annualise([(date(2018, 1, 1), D("1000")), (date(2019, 1, 1), D("-5"))], 5).valeur, -1.0)
        self.assertIsNone(mesures.rendement_annualise(serie[:1], 5).valeur)


class TestBilan(unittest.TestCase):
    def test_bilan_d_une_annee_calcule_a_la_main(self):
        trades = [trade("10", date(2018, 2, 1)), trade("-4", date(2018, 6, 1)), trade("6", date(2018, 12, 31)),
                  trade("99", date(2019, 1, 2))]  # le dernier est clos en 2019 : hors de 2018
        valeurs = [(date(2018, 2, 1), D("1010")), (date(2018, 6, 1), D("950")), (date(2018, 12, 31), D("1012")),
                   (date(2019, 1, 2), D("1111"))]
        b = mesure.bilan(trades, valeurs, date(2018, 1, 1), date(2018, 12, 31), 1000)
        self.assertEqual((b.trades, b.resultat_net, b.resultat_brut, b.frais, b.esperance), (3, 12.0, 18.0, 6.0, 4.0))
        self.assertAlmostEqual(b.taux_reussite, 2 / 3)
        self.assertEqual(b.profit_factor, 4.0)  # 16 de gains pour 4 de pertes
        self.assertAlmostEqual(b.part_frais, 6 / 18)
        self.assertEqual((b.valeur_debut, b.valeur_fin), (1000.0, 1012.0))  # part du capital, la veille du 1er janvier
        self.assertAlmostEqual(b.rendement, 0.012)
        self.assertAlmostEqual(b.drawdown_max, 950 / 1010 - 1)
        self.assertAlmostEqual(b.rendement_annualise, 1.012 ** (365.25 / 365) - 1)
        self.assertAlmostEqual(b.ratio, b.rendement_annualise / abs(b.drawdown_max))
        suivant = mesure.bilan(trades, valeurs, date(2019, 1, 1), date(2019, 12, 31), 1000)
        self.assertEqual((suivant.trades, suivant.valeur_debut, suivant.valeur_fin), (1, 1012.0, 1111.0))

    def test_compte_passe_sous_zero(self):
        # un compte ruiné par ses frais : la valeur négative est mesurée telle quelle
        valeurs = [(date(2018, 6, 1), D("400")), (date(2018, 12, 31), D("-50"))]
        b = mesure.bilan([], valeurs, date(2018, 1, 1), date(2018, 12, 31), 1000)
        self.assertEqual((b.valeur_fin, b.rendement_annualise), (-50.0, -1.0))  # −100 % par an
        self.assertAlmostEqual(b.rendement, -1.05)
        self.assertAlmostEqual(b.drawdown_max, -1.05)
        self.assertAlmostEqual(b.ratio, -1.0 / 1.05)

    def test_sans_trade_ni_valeur_rien_n_est_zero(self):
        b = mesure.bilan([], [], date(2018, 1, 1), date(2018, 12, 31), 1000)
        self.assertEqual((b.trades, b.resultat_net, b.esperance, b.intervalle, b.taux_reussite, b.rendement,
                          b.drawdown_max, b.ratio), (0, None, None, None, None, None, None, None))
        self.assertEqual(mesure.annee(2026, date(2026, 11, 23)), (date(2026, 1, 1), date(2026, 11, 23)))
        strat = [(date(2018, 1, 2), D("1100"))]
        ref = [(date(2018, 1, 2), D("1300"))]
        self.assertAlmostEqual(mesure.ecart(strat, ref, date(2018, 1, 1), date(2018, 12, 31), 1000), -0.2)


def bilan(**champs) -> mesure.Bilan:
    base = dict(debut=date(2018, 1, 1), fin=date(2025, 12, 31), trades=400, resultat_net=800.0, resultat_brut=1600.0,
                frais=800.0, esperance=2.0, intervalle=(0.5, 3.5), taux_reussite=0.5, profit_factor=1.5, part_frais=0.5,
                valeur_debut=1000.0, valeur_fin=1800.0, rendement=0.8, rendement_annualise=0.076, drawdown_max=-0.10,
                ratio=0.76)
    return mesure.Bilan(**{**base, **champs})


class TestVerdict(unittest.TestCase):
    def annees(self, nets: list[float]) -> dict:
        return {2018 + i: bilan(trades=50, resultat_net=n, esperance=n / 50) for i, n in enumerate(nets)}

    def rendre(self, periode=None, ref_a=None, ref_p=None, nets=(100, 100, 100, 100, 100, 100, 100, 100)):
        return verdict.rendre(periode or bilan(), ref_a or bilan(ratio=0.5), ref_p or bilan(ratio=0.3),
                              self.annees(list(nets)))

    def test_utile_si_les_trois_conditions_sont_vraies(self):
        rendu, conditions = self.rendre()
        self.assertEqual((rendu, [c.vraie for c in conditions], [c.numero for c in conditions]),
                         ("utile", [True, True, True], [1, 2, 3]))
        self.assertIn("espérance nette +2,00 € par trade sur 400 trades", conditions[0].constat)
        self.assertIn("de +0,50 € à +3,50 €", conditions[0].constat)

    def test_sans_avantage_des_qu_une_condition_est_fausse(self):
        cas = [
            (dict(periode=bilan(intervalle=(-0.1, 3.5))), [False, True, True]),   # l'intervalle touche zéro
            (dict(periode=bilan(esperance=-1.0, intervalle=(-2.0, -0.1))), [False, True, True]),
            (dict(ref_a=bilan(ratio=0.9)), [True, False, True]),                  # une seule référence fait mieux
            (dict(ref_p=bilan(ratio=0.76)), [True, False, True]),                 # égalité : pas « supérieur »
            (dict(periode=bilan(ratio=None)), [True, False, True]),               # ratio non calculable
            (dict(nets=(100, 100, 100, -50, -50, -50, -50, -50)), [True, True, False]),   # 3 années positives sur 8
            (dict(nets=(900, 10, 10, 10, -300, -300, -200, -100)), [True, True, False]),  # négatif sans la meilleure
        ]
        for arguments, attendu in cas:
            with self.subTest(attendu=attendu, arguments=sorted(arguments)):
                rendu, conditions = self.rendre(**arguments)
                self.assertEqual((rendu, [c.vraie for c in conditions]), ("sans avantage", attendu))
        _, conditions = self.rendre(nets=(900, 10, 10, 10, -300, -300, -200, -100))
        self.assertIn("positive dans 4 des 8 années", conditions[2].constat)
        self.assertIn("sans la meilleure année (2018) : −870,00 €", conditions[2].constat)

    def test_non_decidable_sous_cent_trades(self):
        rendu, conditions = self.rendre(periode=bilan(trades=99))
        self.assertEqual((rendu, len(conditions), P.MIN_TRADES), ("non décidable", 3, 100))
        self.assertEqual(self.rendre(periode=bilan(trades=100))[0], "utile")
        vide = replace(bilan(), trades=0, esperance=None, intervalle=None, ratio=None, resultat_net=None)
        rendu, conditions = verdict.rendre(vide, bilan(), bilan(), {2018: vide})
        self.assertEqual((rendu, [c.vraie for c in conditions]), ("non décidable", [False, False, False]))
        self.assertIn("non calculable", conditions[0].constat)


if __name__ == "__main__":
    unittest.main()
