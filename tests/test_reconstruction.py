"""
tests/test_reconstruction.py — Appariement des exécutions en trades clos (mesures/reconstruction.py).

Réécriture en unittest de tests/test_reconstruction.py de la source (pytest) : 5 tests, 5 cas,
mêmes valeurs attendues.
1. aller-retour long avec coûts et risque au stop initial ;
2. vente à découvert ;
3. premier entré premier sorti, sortie partielle ;
4. retournement d'une position longue en position courte ;
5. symboles séparés, trade sans stop initial.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_reconstruction -v
Calcul pur sur des objets inventés : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from ledger import Execution
from mesures import reconstruire
from tests.socle_fixtures import jour


def ex(i, sens, q, prix, j, couts="0", stop=None, sym="AAA"):
    return Execution(i, 1, sym, jour(j), sens, D(q), D(prix), "USD", D(couts),
                     None if stop is None else D(stop), "regles")


class TestReconstruction(unittest.TestCase):
    def test_aller_retour_long_avec_couts_et_risque(self):
        clos, ouvertes = reconstruire([
            ex(1, "achat", "10", "100", 1, couts="1", stop="95"),
            ex(2, "vente", "10", "110", 2, couts="1")])
        self.assertEqual(ouvertes, [])
        t = clos[0]
        self.assertEqual((t.sens, t.pnl_brut, t.couts, t.pnl_net), ("long", D("100"), D("2"), D("98")))
        self.assertEqual(t.risque, D("50"))
        self.assertEqual(t.r, D("1.96"))

    def test_vente_a_decouvert(self):
        clos, _ = reconstruire([ex(1, "vente", "5", "100", 1, stop="104"),
                                ex(2, "achat", "5", "90", 2)])
        self.assertEqual((clos[0].sens, clos[0].pnl_brut, clos[0].risque), ("court", D("50"), D("20")))

    def test_fifo_et_sortie_partielle(self):
        clos, ouvertes = reconstruire([
            ex(1, "achat", "10", "100", 1, couts="2"),
            ex(2, "achat", "10", "120", 2),
            ex(3, "vente", "15", "130", 3, couts="3")])
        self.assertEqual([(t.quantite, t.prix_entree, t.pnl_brut) for t in clos],
                         [(D("10"), D("100"), D("300")), (D("5"), D("120"), D("50"))])
        self.assertEqual([t.couts for t in clos], [D("4"), D("1")])
        self.assertEqual([(p.sens, p.quantite, p.prix_entree) for p in ouvertes],
                         [("long", D("5"), D("120"))])

    def test_retournement_long_vers_court(self):
        clos, ouvertes = reconstruire([ex(1, "achat", "10", "100", 1),
                                       ex(2, "vente", "15", "110", 2)])
        self.assertEqual(len(clos), 1)
        self.assertEqual(clos[0].quantite, D("10"))
        self.assertEqual([(p.sens, p.quantite) for p in ouvertes], [("court", D("5"))])

    def test_symboles_separes_et_sans_stop(self):
        clos, ouvertes = reconstruire([ex(1, "achat", "1", "10", 1),
                                       ex(2, "vente", "1", "20", 2, sym="BBB")])
        self.assertEqual(clos, [])
        self.assertEqual(len(ouvertes), 2)
        clos, _ = reconstruire([ex(1, "achat", "1", "10", 1), ex(2, "vente", "1", "20", 2)])
        self.assertIsNone(clos[0].risque)
        self.assertIsNone(clos[0].r)


if __name__ == "__main__":
    unittest.main()
