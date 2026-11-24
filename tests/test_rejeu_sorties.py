"""
tests/test_rejeu_sorties.py — Sorties sur une barre et frais du rejeu (rejeu/sorties.py, frais.py).

1. stop ou objectif touché par le bas ou le haut de la barre, position longue et vente à découvert ;
2. stop et objectif touchés le même jour : le stop est pris ;
3. ouverture au-delà du stop : exécution à l'ouverture ; au-delà de l'objectif : au prix de
   l'objectif, pas mieux ; le jour de l'entrée, l'ouverture n'est pas un écart ;
4. frais « Revolut » : 1 € par ordre ; frais « CFD » : écart par côté selon le type du titre,
   financement par nuit sur le montant d'entrée.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_sorties -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from rejeu import frais, sorties


class TestSorties(unittest.TestCase):
    def sortie(self, direction, o, h, b, c, stop, objectif, **kw):
        s = sorties.tester(direction, stop, objectif, o, h, b, c, **kw)
        return None if s is None else (s.prix, s.statut)

    def test_position_longue(self):
        for barre, attendu in [((100, 101, 99, 100), None), ((100, 101, 96.5, 98), (97, "CLOSED_SL")),
                               ((100, 107, 99, 105), (106, "CLOSED_TP")),
                               ((100, 107, 96, 100), (97, "CLOSED_SL")),   # les deux le même jour : le stop
                               ((96, 98, 95, 97.5), (96, "CLOSED_SL")),    # ouverture sous le stop : à l'ouverture
                               ((108, 109, 107, 108), (106, "CLOSED_TP")),  # ouverture au-dessus : pas mieux que l'objectif
                               ((100, 99.5, 99, 100), None)]:              # haut sous l'ouverture : on garde l'ouverture
            with self.subTest(barre=barre):
                self.assertEqual(self.sortie("LONG", *barre, stop=97, objectif=106), attendu)

    def test_vente_a_decouvert(self):
        for barre, attendu in [((100, 101, 99, 100), None), ((100, 103.5, 99, 102), (103, "CLOSED_SL")),
                               ((100, 101, 93, 95), (94, "CLOSED_TP")), ((100, 104, 93, 100), (103, "CLOSED_SL")),
                               ((104, 105, 103.5, 104), (104, "CLOSED_SL")), ((92, 93, 91, 92), (94, "CLOSED_TP"))]:
            with self.subTest(barre=barre):
                self.assertEqual(self.sortie("SHORT", *barre, stop=103, objectif=94), attendu)

    def test_le_jour_de_l_entree_l_ouverture_n_est_pas_un_ecart(self):
        # entrée à l'ouverture (100) : seuls le haut et le bas de la séance comptent
        self.assertIsNone(self.sortie("LONG", 100, 101, 97.5, 100, stop=97, objectif=106, entree_ce_jour=True))
        self.assertEqual(self.sortie("LONG", 100, 101, 96, 99, stop=97, objectif=106, entree_ce_jour=True),
                         (97, "CLOSED_SL"))
        self.assertEqual(self.sortie("LONG", 100, 107, 99, 105, stop=97, objectif=106, entree_ce_jour=True),
                         (106, "CLOSED_TP"))
        # un stop égal à l'ouverture d'entrée ne sort pas « à l'ouverture » : il est servi à son prix
        self.assertEqual(self.sortie("SHORT", 103, 103, 100, 101, stop=103, objectif=94, entree_ce_jour=True),
                         (103, "CLOSED_SL"))
        with self.assertRaises(ValueError):
            sorties.tester("NEUTRE", 1, 2, 1, 1, 1, 1)


class TestFrais(unittest.TestCase):
    ENTREE, SORTIE = date(2030, 1, 7), date(2030, 1, 10)  # 3 nuits

    def test_revolut_un_euro_par_ordre(self):
        self.assertEqual(frais.entree("revolut", "AAPL", 0.5, 100.0), [("commission", D("1"))])
        self.assertEqual(frais.sortie("revolut", "BTC-USD", 0.5, 106.0, 100.0, self.ENTREE, self.SORTIE),
                         [("commission", D("1"))])
        self.assertEqual(frais.total(frais.entree("revolut", "AAPL", 1, 1)), D("1"))

    def test_cfd_ecart_par_type_et_financement_par_nuit(self):
        for ticker, type_, taux in [("AAPL", "action", "0.001"), ("SPY", "etf", "0.001"), ("BTC-USD", "crypto", "0.005"),
                                    ("GC=F", "cfd", "0.005")]:
            with self.subTest(ticker=ticker):
                self.assertEqual(frais.type_titre(ticker), type_)
                self.assertEqual(frais.entree("cfd", ticker, 0.5, 100.0), [("spread", D(taux) * D("50"))])
        couts = dict(frais.sortie("cfd", "AAPL", 0.5, 106.0, 100.0, self.ENTREE, self.SORTIE))
        self.assertEqual(couts, {"spread": D("0.001") * D("53"), "financement": D("0.0002") * D("50") * 3})
        self.assertEqual(frais.total(list(couts.items())), D("0.083"))
        self.assertEqual((frais.nuits(self.ENTREE, self.ENTREE), frais.nuits(self.ENTREE, self.SORTIE)), (0, 3))
        sans_nuit = frais.sortie("cfd", "AAPL", 0.5, 106.0, 100.0, self.ENTREE, self.ENTREE)
        self.assertEqual([t for t, _ in sans_nuit], ["spread"])  # sorti le jour même : aucun financement


if __name__ == "__main__":
    unittest.main()
