"""
tests/test_mesures.py — Mesures sur les trades clos et sur la valeur quotidienne (mesures/).

Réécriture en unittest de tests/test_mesures.py de la source (pytest) : 6 tests, 6 cas,
mêmes valeurs attendues ; pytest.approx devient assertProche (même tolérance).
1. valeurs connues : résultat net, taux de réussite, payoff, profit factor, part des coûts,
   espérance en R ;
2. période de la mesure et seuil de 100 trades (99 : non décidable ; 100 : décidable) ;
3. mesure sans dénominateur : valeur None, jamais d'exception ;
4. devises mélangées refusées ;
5. courbe : rendement, drawdown max, Sharpe, Sortino, écart au benchmark ;
6. courbe : cas limites et levier.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_mesures -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import mesures as m
from tests.socle_fixtures import Proche, jour


def t(pnl, couts="0", risque=None, devise="USD", j=1):
    return m.TradeClos(1, "AAA", "long", D("1"), D("100"), D("100") + D(pnl),
                       jour(j), jour(j + 1), devise, D(pnl), D(couts),
                       None if risque is None else D(risque))


TRADES = [t("30", "2", "10"), t("10", "2", "10", j=3), t("-18", "2", "10", j=5),
          t("-8", "2", j=7)]  # nets : 28, 8, -20, -10


def serie(*valeurs):
    return [(date(2030, 1, 1) + timedelta(days=i), D(str(v)))
            for i, v in enumerate(valeurs)]


class TestMesuresSurTrades(Proche, unittest.TestCase):
    def test_valeurs_connues(self):
        self.assertEqual(m.resultat_net(TRADES).valeur, 6)
        self.assertEqual(m.taux_reussite(TRADES).valeur, 0.5)
        self.assertProche(m.payoff(TRADES).valeur, 18 / 15)
        self.assertProche(m.profit_factor(TRADES).valeur, 36 / 30)
        self.assertProche(m.part_des_couts(TRADES).valeur, 8 / 14)
        e = m.esperance_r(TRADES)
        self.assertProche(e.valeur, (2.8 + 0.8 - 2.0) / 3)
        self.assertEqual(e.n, 3)

    def test_periode_et_seuil_de_100_trades(self):
        r = m.resultat_net(TRADES)
        self.assertEqual((r.n, r.debut, r.fin), (4, date(2030, 1, 1), date(2030, 1, 8)))
        self.assertFalse(r.decidable)
        self.assertIn("4 trades sur 100", r.raison)
        self.assertFalse(m.resultat_net([t("1")] * 99).decidable)
        self.assertTrue(m.resultat_net([t("1")] * 100).decidable)

    def test_sans_denominateur_pas_d_exception(self):
        gagnants = [t("5")] * 100
        for f in (m.payoff, m.profit_factor):
            self.assertIsNone(f(gagnants).valeur)
            self.assertFalse(f(gagnants).decidable)
        self.assertIsNone(m.part_des_couts([t("-5", "1")]).valeur)
        self.assertIsNone(m.esperance_r([t("5")]).valeur)
        for mes in m.tableau([]):
            self.assertIsNone(mes.valeur)
            self.assertEqual(mes.n, 0)
            self.assertFalse(mes.decidable)

    def test_devises_melangees_refusees(self):
        with self.assertRaisesRegex(ValueError, "devises mélangées"):
            m.resultat_net([t("1"), t("1", devise="EUR")])


class TestMesuresSurLaCourbe(Proche, unittest.TestCase):
    def test_courbe_valeurs_connues(self):
        s = serie(100, 120, 90, 110)
        self.assertProche(m.rendement(s, 100).valeur, 0.10)
        self.assertProche(m.drawdown_max(s, 100).valeur, -0.25)
        self.assertTrue(m.rendement(s, 100).decidable)
        self.assertFalse(m.rendement(s, 5).decidable)
        self.assertGreater(m.sharpe(s, 100).valeur, 0)
        self.assertGreater(m.sortino(s, 100).valeur, 0)
        b = serie(100, 100, 100, 105)
        self.assertProche(m.ecart_au_benchmark(s, b, 100).valeur, 0.05)

    def test_courbe_cas_limites(self):
        self.assertIsNone(m.rendement(serie(100), 100).valeur)
        self.assertIsNone(m.sharpe(serie(100, 100, 100), 100).valeur)
        self.assertIsNone(m.sortino(serie(100, 110, 121), 100).valeur)
        self.assertEqual(m.drawdown_max(serie(100, 110, 121), 100).valeur, 0)
        self.assertIsNone(m.ecart_au_benchmark(serie(100, 110), [], 100).valeur)
        self.assertEqual(m.levier(D("5000"), D("1000")), 5.0)
        self.assertIsNone(m.levier(D("1"), D("0")))


if __name__ == "__main__":
    unittest.main()
