"""
tests/test_ledger_taux.py — Script manuel scripts/ledger_taux.py.

1. À blanc par défaut : le rapport est affiché, rien n'est écrit, le grand livre n'est pas créé ;
   période par défaut de 365 jours jusqu'à hier ; --appliquer écrit ; relance : aucun doublon,
   période reprise 7 jours avant le dernier taux ;
2. cours indisponible : code 1, erreur claire, aucun taux écrit ;
3. options --depuis et --jusqu-a ; période vide refusée.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_ledger_taux -v
Source de cours simulée, taux inventés ; base dans un dossier temporaire ; aucun réseau (toute
connexion lève une erreur), aucun .env, rien dans data/ : le script n'est jamais lancé sur son
chemin par défaut.
"""

import contextlib
import io
import os
import sqlite3
import sys
import unittest
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from importeurs import taux_change as tc
from scripts import ledger_taux as script
from tests.socle_taux_fixtures import AUJOURD_HUI, SansReseau, source


class TestScript(SansReseau):
    def setUp(self):
        super().setUp()
        self.conn.close()  # le script ouvre lui-même son grand livre
        self.livre = os.path.join(self.dossier.name, "livre", "ledger.db")
        os.makedirs(os.path.dirname(self.livre))

    def lancer(self, telecharger, **kw):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = script.lancer(self.livre, telecharger=telecharger, aujourd_hui=AUJOURD_HUI, **kw)
        return code, sortie.getvalue()

    def nb_taux(self) -> int:
        conn = sqlite3.connect(self.livre)
        try:
            return conn.execute("SELECT COUNT(*) FROM change").fetchone()[0]
        finally:
            conn.close()

    def test_a_blanc_par_defaut_puis_appliquer(self):
        src = source()
        code, texte = self.lancer(src)
        self.assertEqual(code, 0)
        self.assertIn("À BLANC", texte)
        self.assertIn("jours ajoutés      : 3", texte)
        self.assertEqual(src.appels, [(date(2029, 1, 10), date(2030, 1, 9))])  # 365 jours, jusqu'à hier
        self.assertEqual(os.listdir(os.path.dirname(self.livre)), [])  # aucun grand livre créé
        code, texte = self.lancer(source(), appliquer=True)
        self.assertEqual((code, self.nb_taux()), (0, 3))
        src = source()
        code, texte = self.lancer(src, appliquer=True)  # relance : depuis 7 jours avant le dernier taux
        self.assertEqual(src.appels, [(date(2030, 1, 2), date(2030, 1, 9))])
        self.assertIn("jours déjà présents : 3", texte)
        self.assertEqual((code, self.nb_taux()), (0, 3))

    def test_cours_indisponible(self):
        def en_panne(debut, fin):
            raise tc.SourceIndisponible("cours EURUSD=X indisponible : réseau coupé")
        code, texte = self.lancer(en_panne, appliquer=True)
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", texte)
        self.assertIn("Rien n'a été écrit", texte)
        self.assertEqual(self.nb_taux(), 0)

    def test_options_de_la_ligne_de_commande(self):
        src = source([(date(2020, 3, 2), 1.11), (date(2020, 3, 3), 1.12)])  # dates passées, taux inventés
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = script.main(["--ledger", self.livre, "--depuis", "2020-03-01", "--jusqu-a", "2020-03-05",
                                "--appliquer"], telecharger=src)
        self.assertEqual((code, self.nb_taux()), (0, 2))
        self.assertEqual(src.appels, [(date(2020, 3, 1), date(2020, 3, 5))])
        with contextlib.redirect_stdout(io.StringIO()) as vide:
            code = script.main(["--ledger", self.livre, "--depuis", "2020-03-05", "--jusqu-a", "2020-03-01"],
                               telecharger=src)
        self.assertEqual(code, 1)
        self.assertIn("période vide", vide.getvalue())


if __name__ == "__main__":
    unittest.main()
