"""
tests/test_trade_journalist.py — Démo isolée et numérotation des signaux (TODO : signal_results).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_trade_journalist -v
Sans .env, sans réseau. Pendant le test, DB_PATH et les fichiers mémoire pointent
vers des fichiers témoins : une démo qui écrirait « en production » les modifierait.
"""

import contextlib
import hashlib
import io
import logging
import os
import re
import runpy
import sqlite3
import sys
import tempfile
import unittest
import warnings
from datetime import datetime, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

from utils import database
from utils.portfolio_db import initialiser_paper_db
from agents.trade_journalist import journalist
from agents.trade_journalist.demo_performance import SIGNAUX_DEMO, _CHEMINS

BASE_REELLE = database.DB_PATH  # data/database.db, jamais ouverte en écriture ici


def _empreinte(chemin: str) -> str | None:
    if not os.path.exists(chemin):
        return None
    with open(chemin, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestDemoIsolee(unittest.TestCase):
    """La démo de performance_tracker ne modifie ni DB_PATH ni les fichiers mémoire."""

    def setUp(self):
        logging.disable(logging.CRITICAL)  # pas de « SIG-0001 enregistré » dans logs/ de production
        self.dossier = tempfile.TemporaryDirectory()
        self.patchs, chemins = [], set()
        for module, attribut, nom in _CHEMINS:
            chemin = os.path.join(self.dossier.name, "temoin_" + nom)
            if attribut != "DB_PATH":
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write("fichier mémoire de production simulé\n")
            chemins.add(chemin)
            self.patchs.append(mock.patch.object(module, attribut, chemin))
        for p in self.patchs:
            p.start()
        # Base témoin avec le vrai schéma : une démo non isolée y écrirait sans erreur
        database.initialiser_base()
        initialiser_paper_db()
        self.temoins = {c: _empreinte(c) for c in chemins}

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()
        logging.disable(logging.NOTSET)

    def test_demo_ne_modifie_pas_db_path(self):
        debut = datetime.now(timezone.utc).isoformat()
        temoin_db = database.DB_PATH
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), warnings.catch_warnings():
            # Module déjà importé (demo_performance) : runpy en exécute une copie, comme python -m
            warnings.simplefilter("ignore", RuntimeWarning)
            runpy.run_module("agents.trade_journalist.performance_tracker", run_name="__main__")
        texte = sortie.getvalue()

        self.assertIn("'nb_trades': 3", texte)  # la démo a bien tourné, dans sa propre base
        self.assertEqual(database.DB_PATH, temoin_db)  # chemins restaurés après la démo
        for chemin, empreinte in self.temoins.items():
            self.assertEqual(_empreinte(chemin), empreinte, f"{os.path.basename(chemin)} modifié par la démo")
        dossier_demo = re.search(r"Démo isolée dans (\S+) :", texte).group(1)
        self.assertFalse(os.path.exists(dossier_demo), "dossier temporaire de la démo non supprimé")

        # Base réelle : aucun signal de démo écrit pendant le test (lecture seule ; absente en worktree)
        if os.path.exists(BASE_REELLE):
            conn = sqlite3.connect(f"file:{BASE_REELLE}?mode=ro", uri=True)
            n = conn.execute(f"SELECT COUNT(*) FROM signals WHERE timestamp >= ? AND reason IN "
                             f"({','.join('?' * len(SIGNAUX_DEMO))})", (debut, *[s[-1] for s in SIGNAUX_DEMO])).fetchone()[0]
            conn.close()
            self.assertEqual(n, 0)


class TestIdentifiantSignal(unittest.TestCase):
    """generer_signal_id : plus grand numéro + 1, jamais un numéro déjà pris."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.dossier = tempfile.TemporaryDirectory()
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "t.db")),
                       mock.patch.object(journalist, "JOURNAL_FILE", os.path.join(self.dossier.name, "j.md"))]
        for p in self.patchs:
            p.start()
        database.initialiser_base()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()
        logging.disable(logging.NOTSET)

    def _enregistrer(self, n: int) -> list[str]:
        return [journalist.enregistrer_signal(*SIGNAUX_DEMO[i % len(SIGNAUX_DEMO)]) for i in range(n)]

    def _supprimer(self, *ids: str) -> None:
        conn = sqlite3.connect(database.DB_PATH)
        conn.executemany("DELETE FROM signals WHERE signal_id = ?", [(i,) for i in ids])
        conn.commit()
        conn.close()

    def test_table_vide(self):
        self.assertEqual(journalist.generer_signal_id(), "SIG-0001")

    def test_suppression_au_milieu(self):
        self.assertEqual(self._enregistrer(5), [f"SIG-000{i}" for i in range(1, 6)])
        self._supprimer("SIG-0003")
        self.assertEqual(journalist.generer_signal_id(), "SIG-0006")  # COUNT(*) + 1 donnait SIG-0005
        self.assertEqual(self._enregistrer(1), ["SIG-0006"])  # insertion réussie, pas de collision
        conn = sqlite3.connect(database.DB_PATH)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 5)
        conn.close()

    def test_suppression_des_premiers(self):
        """Cas de la purge de SIG-0001 à SIG-0005 : la suite reprend après le plus grand numéro."""
        self._enregistrer(8)
        self._supprimer(*[f"SIG-000{i}" for i in range(1, 6)])
        self.assertEqual(self._enregistrer(1), ["SIG-0009"])


if __name__ == "__main__":
    unittest.main()
