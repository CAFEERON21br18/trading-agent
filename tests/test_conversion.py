"""
tests/test_conversion.py — Bascule euro/dollar au taux stocké (mesures/conversion.py).

Réécriture en unittest de tests/test_conversion.py de la source (pytest) : 4 tests, 4 cas,
mêmes valeurs attendues.
1. conversion dans les deux sens, sans conversion pour une même devise ;
2. week-end : dernier taux connu, jusqu'à 7 jours en arrière ;
3. taux manquant (trop ancien, ou futur) et devise inconnue : erreur explicite ;
4. en_devise convertit résultat, coûts et risque, et garde le résultat en R.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_conversion -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from mesures import TauxManquant, TradeClos, convertir, en_devise, taux_du_jour
from tests.socle_fixtures import jour

TAUX = {date(2030, 1, 4): D("1.25")}


class TestConversion(unittest.TestCase):
    def test_conversion_dans_les_deux_sens(self):
        j = date(2030, 1, 4)
        self.assertEqual(convertir(D("100"), "EUR", "USD", j, TAUX), D("125"))
        self.assertEqual(convertir(D("125"), "USD", "EUR", j, TAUX), D("100"))
        self.assertEqual(convertir(D("7"), "USD", "USD", j, {}), D("7"))

    def test_week_end_reprend_le_dernier_taux(self):
        self.assertEqual(taux_du_jour(TAUX, date(2030, 1, 6)), D("1.25"))
        self.assertEqual(taux_du_jour(TAUX, date(2030, 1, 11)), D("1.25"))

    def test_taux_manquant_ou_devise_inconnue(self):
        with self.assertRaises(TauxManquant):
            taux_du_jour(TAUX, date(2030, 1, 12))
        with self.assertRaises(TauxManquant):
            taux_du_jour(TAUX, date(2030, 1, 3))
        with self.assertRaises(ValueError):
            convertir(D("1"), "GBP", "EUR", date(2030, 1, 4), TAUX)

    def test_en_devise_convertit_resultat_couts_et_risque(self):
        t = TradeClos(1, "AAA", "long", D("1"), D("100"), D("225"), jour(3), jour(4),
                      "USD", D("125"), D("2.5"), D("25"))
        c = en_devise([t], "EUR", TAUX)[0]
        self.assertEqual((c.devise, c.pnl_brut, c.couts, c.risque), ("EUR", D("100"), D("2"), D("20")))
        self.assertEqual(c.r, t.r)
        self.assertEqual(en_devise([t], "USD", {}), [t])


if __name__ == "__main__":
    unittest.main()
