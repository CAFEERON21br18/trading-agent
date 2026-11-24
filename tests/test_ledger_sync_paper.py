"""
tests/test_ledger_sync_paper.py — Script manuel scripts/ledger_sync_paper.py.

1. À blanc par défaut : le rapport est affiché, rien n'est écrit, le grand livre n'est pas créé ;
2. --appliquer écrit ; relancer n'ajoute aucun doublon ; à blanc sur un grand livre existant :
   rien n'est ajouté ;
3. sans la colonne « boucle » : code 1, erreur claire, aucun grand livre créé ;
4. position illisible : code 1, la position est nommée, rien n'est écrit ;
5. chemins par défaut : data/database.db (lue) et data/ledger.db (hors git).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_ledger_sync_paper -v
Bases fabriquées dans un dossier temporaire, positions inventées ; aucun réseau, aucun .env,
rien dans data/ : le script n'est jamais lancé sur ses chemins par défaut.
"""

import contextlib
import io
import os
import sqlite3
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from scripts import ledger_sync_paper as script
from tests.socle_paper_fixtures import BasePaperLedger, creer_base, executer, position


class TestScript(BasePaperLedger):
    def setUp(self):
        super().setUp()
        self.livre = os.path.join(self.dossier.name, "livre", "ledger.db")
        os.makedirs(os.path.dirname(self.livre))

    def lancer(self, *options, base=None):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = script.main(["--base", base or self.base, "--ledger", self.livre, *options])
        return code, sortie.getvalue()

    def nb_trades_du_livre(self) -> int:
        conn = sqlite3.connect(self.livre)
        try:
            return conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        finally:
            conn.close()

    def test_a_blanc_par_defaut(self):
        position(self.base, "AAA")
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("À BLANC", texte)
        self.assertIn("exécutions ajoutées             : 2", texte)
        self.assertEqual(os.listdir(os.path.dirname(self.livre)), [])  # aucun grand livre créé

    def test_appliquer_puis_relance_sans_doublon(self):
        position(self.base, "AAA")
        position(self.base, "^FCHI", statut="OPEN")
        code, texte = self.lancer("--appliquer")
        self.assertEqual(code, 0)
        self.assertIn("Synchronisation appliquée", texte)
        self.assertIn("devise incertaine, enregistrée en USD par défaut : ^FCHI", texte)
        self.assertEqual(self.nb_trades_du_livre(), 3)
        code, texte = self.lancer("--appliquer")
        self.assertIn("exécutions déjà présentes       : 3", texte)
        self.assertEqual((code, self.nb_trades_du_livre()), (0, 3))
        position(self.base, "BBB")
        code, texte = self.lancer()  # à blanc sur un grand livre existant
        self.assertIn("exécutions ajoutées             : 2", texte)
        self.assertEqual((code, self.nb_trades_du_livre()), (0, 3))

    def test_sans_colonne_boucle(self):
        nue = os.path.join(self.dossier.name, "sans_marquage.db")
        creer_base(nue, boucle=False)
        code, texte = self.lancer("--appliquer", base=nue)
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", texte)
        self.assertIn("marquer_boucles.py --appliquer", texte)
        self.assertIn("Rien n'a été importé", texte)
        self.assertEqual(os.listdir(os.path.dirname(self.livre)), [])

    def test_position_illisible(self):
        position(self.base, "AAA")
        mauvaise = position(self.base, "FFF")
        executer(self.base, "UPDATE positions SET exit_date = NULL WHERE id = ?", (mauvaise,))
        code, texte = self.lancer("--appliquer")
        self.assertEqual(code, 1)
        self.assertIn(f"position #{mauvaise} : date de sortie", texte)
        self.assertEqual(self.nb_trades_du_livre(), 0)

    def test_chemins_par_defaut(self):
        self.assertEqual(os.path.normcase(script.BASE_DEFAUT),
                         os.path.normcase(os.path.join(RACINE, "data", "database.db")))
        self.assertEqual(os.path.normcase(script.LEDGER_DEFAUT),
                         os.path.normcase(os.path.join(RACINE, "data", "ledger.db")))


if __name__ == "__main__":
    unittest.main()
