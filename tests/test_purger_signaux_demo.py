"""
tests/test_purger_signaux_demo.py — scripts/purger_signaux_demo.py, sur une base temporaire.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_purger_signaux_demo -v
Sans .env, sans réseau. La base est construite par la démo isolée (mêmes valeurs
que la démo du 15/04/2026) ; data/database.db n'est jamais ouverte.
"""

import contextlib
import io
import logging
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

from utils import database
from agents.trade_journalist import journalist, performance_tracker
from agents.trade_journalist.demo_performance import SIGNAUX_DEMO, environnement_isole, inserer_donnees_demo
from scripts import purger_signaux_demo as purge


def _ancien_generer_signal_id() -> str:
    conn = database.get_connection()
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    return f"SIG-{n + 1:04d}"


class TestPurge(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.pile = contextlib.ExitStack()
        self.pile.enter_context(environnement_isole())
        self.sauvegardes = self.pile.enter_context(tempfile.TemporaryDirectory(ignore_cleanup_errors=True))
        self.pile.enter_context(mock.patch.object(purge, "DOSSIER_SAUVEGARDES", self.sauvegardes))
        self.pile.enter_context(mock.patch.object(purge, "copie_ignoree", return_value=True))
        inserer_donnees_demo()                                         # SIG-0001 à SIG-0005
        for s in SIGNAUX_DEMO[:3]:                                     # SIG-0006 à SIG-0008 : « production »
            journalist.enregistrer_signal(*s[:-1], "signal de production")
        journalist.cloturer_signal("SIG-0006", 80000.0, "résultat de production")

    def tearDown(self):
        self.pile.close()
        logging.disable(logging.NOTSET)

    def _lancer(self, appliquer: bool) -> tuple[int, str]:
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = purge.main(appliquer)
        return code, sortie.getvalue()

    def _ids(self, table: str) -> list[str]:
        conn = sqlite3.connect(database.DB_PATH)
        ids = [r[0] for r in conn.execute(f"SELECT signal_id FROM {table} ORDER BY signal_id")]
        conn.close()
        return ids

    def _rien_supprime(self):
        self.assertEqual(self._ids("signals"), [f"SIG-000{i}" for i in range(1, 9)])
        self.assertEqual(self._ids("signal_results"), ["SIG-0001", "SIG-0002", "SIG-0003", "SIG-0006"])

    def test_a_blanc_n_ecrit_rien(self):
        code, texte = self._lancer(False)
        self.assertEqual(code, 0)
        self.assertIn("[2] valeurs identiques à la démo : oui", texte)
        self.assertIn("3 ligne(s) de signal_results (sur 4), 5 de signals (sur 8)", texte)
        self._rien_supprime()
        self.assertEqual(os.listdir(self.sauvegardes), [])

    def test_purge_complete(self):
        code, texte = self._lancer(True)
        self.assertEqual(code, 0, texte)
        self.assertEqual(self._ids("signals"), ["SIG-0006", "SIG-0007", "SIG-0008"])
        self.assertEqual(self._ids("signal_results"), ["SIG-0006"])  # résultat de production conservé
        sauvegarde = os.path.join(self.sauvegardes, os.listdir(self.sauvegardes)[0])
        self.assertRegex(os.path.basename(sauvegarde), r"^database_avant_purge_demo_\d{8}\.db$")
        conn = sqlite3.connect(sauvegarde)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 8)
        conn.close()
        with open(performance_tracker.PERFORMANCE_FILE, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| BTC-USD | 1 | 1 | 100.0% |", md)            # SIG-0006 seul
        self.assertNotIn("ETH-USD", md)
        self.assertNotIn("AAPL", md)
        self.assertEqual(journalist.generer_signal_id(), "SIG-0009")
        self.assertEqual(self._lancer(True)[0], 1)                     # deuxième passage : sauvegarde du jour présente

    def test_valeur_differente_arrete_tout(self):
        conn = sqlite3.connect(database.DB_PATH)
        conn.execute("UPDATE signals SET price_at_signal = 3201.0 WHERE signal_id = 'SIG-0002'")
        conn.commit()
        conn.close()
        code, texte = self._lancer(True)
        self.assertEqual(code, 1)
        self.assertIn("SIG-0002.price_at_signal", texte)
        self._rien_supprime()
        self.assertEqual(os.listdir(self.sauvegardes), [])

    def test_correction_absente_arrete_tout(self):
        with mock.patch.object(journalist, "generer_signal_id", _ancien_generer_signal_id):
            code, texte = self._lancer(True)
        self.assertEqual(code, 1)
        self.assertIn("generer_signal_id non corrigé", texte)
        self._rien_supprime()
        self.assertEqual(os.listdir(self.sauvegardes), [])


if __name__ == "__main__":
    unittest.main()
