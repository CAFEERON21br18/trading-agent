"""
tests/test_regenerer_graphe.py — Phase 3 : régénération de la carte du code (scripts/regenerer_graphe.py)
et dossier du vault (utils/vault_chemin.py).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_regenerer_graphe -v
Graphify, sous-processus et copie dans le vault simulés : aucun appel réel, aucune écriture hors
dossiers temporaires.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from scripts import regenerer_graphe as rg
from utils import vault_chemin

RAPPORT_SANS_LLM = "# Graph Report\n- Token cost: 0 input · 0 output\n"


class TestRegenerer(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.rapport = os.path.join(self.dossier.name, "GRAPH_REPORT.md")
        with open(self.rapport, "w", encoding="utf-8") as f:
            f.write(RAPPORT_SANS_LLM)
        self.appels, self.codes = [], [0, 0]
        self.copies = []

        def run(cmd, **kw):
            self.appels.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, self.codes[len(self.appels) - 1], "fin", "")

        for p in (mock.patch.object(rg, "graphify_disponible", return_value=True),
                  mock.patch.object(rg.subprocess, "run", side_effect=run),
                  mock.patch.object(rg, "RAPPORT", self.rapport),
                  mock.patch("scripts.sync_graphify_vault.sync_vault",
                             side_effect=lambda src, vault: self.copies.append((src, vault)) or [])):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dossier.cleanup)

    def test_trois_etapes_sans_llm(self):
        env = {"GEMINI_API_KEY": "k", "GROQ_API_KEY": "k", "OPENAI_BASE_URL": "u", "PATH": "p"}
        with mock.patch.dict(os.environ, env):
            r = rg.regenerer(vault=self.dossier.name)
        self.assertEqual(r["statut"], "ok")
        self.assertTrue(r["sans_llm"])
        commandes = [c[3:] for c, _ in self.appels]
        self.assertEqual(commandes, [["extract", ".", "--code-only"], ["cluster-only", ".", "--no-label"]])
        for cmd, kw in self.appels:
            self.assertEqual(cmd[:3], [sys.executable, "-m", "graphify"])
            self.assertEqual(kw["cwd"], rg.RACINE)
            self.assertLessEqual(kw["timeout"], 300)  # 2 étapes sous le budget de 10 min du weekly
            self.assertFalse([k for k in kw["env"] if "API_KEY" in k or "BASE_URL" in k])
            self.assertIn("PATH", kw["env"])
        self.assertEqual(self.copies, [(rg.SORTIE, self.dossier.name)])

    def test_cout_non_nul_signale(self):
        with open(self.rapport, "w", encoding="utf-8") as f:
            f.write("- Token cost: 1200 input · 300 output\n")
        with self.assertLogs(rg.logger, "ERROR"):
            r = rg.regenerer(vault=self.dossier.name)
        self.assertFalse(r["sans_llm"])

    def test_etape_en_echec_sans_copie(self):
        self.codes = [2, 0]
        with self.assertLogs(rg.logger, "ERROR"):
            r = rg.regenerer(vault=self.dossier.name)
        self.assertEqual(r["statut"], "echec")
        self.assertEqual(len(self.appels), 1)
        self.assertEqual(self.copies, [])

    def test_delai_depasse_ne_leve_pas(self):
        with mock.patch.object(rg.subprocess, "run", side_effect=subprocess.TimeoutExpired("graphify", 240)):
            r = rg.regenerer(vault=self.dossier.name)
        self.assertEqual(r["statut"], "echec")

    def test_copie_en_erreur_ne_leve_pas(self):
        with mock.patch("scripts.sync_graphify_vault.sync_vault", side_effect=OSError("disque plein")):
            r = rg.regenerer(vault=self.dossier.name)
        self.assertEqual(r["statut"], "echec")

    def test_sans_vault(self):
        r = rg.regenerer(avec_vault=False)
        self.assertEqual((r["statut"], self.copies), ("ok", []))

    def test_graphify_absent(self):
        with mock.patch.object(rg, "graphify_disponible", return_value=False), \
                mock.patch.object(sys, "argv", ["regenerer_graphe.py"]):
            self.assertEqual(rg.regenerer()["statut"], "graphify_absent")
            self.assertEqual(rg.main(), 0)
        self.assertEqual(self.appels, [])

    def test_main_code_1_si_echec(self):
        self.codes = [1, 0]
        with mock.patch.object(sys, "argv", ["regenerer_graphe.py", "--sans-vault"]):
            self.assertEqual(rg.main(), 1)


class TestDossierVault(unittest.TestCase):
    def setUp(self):
        self.racine = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.racine.cleanup)

    def test_variable_d_environnement(self):
        with mock.patch.dict(os.environ, {"ALPHASIGNAL_VAULT": r"D:\Vault"}):
            self.assertEqual(vault_chemin.dossier_vault(self.racine.name), os.path.abspath(r"D:\Vault"))

    def test_cle_du_env_seule(self):
        with open(os.path.join(self.racine.name, ".env"), "w", encoding="utf-8") as f:
            f.write("ALPHASIGNAL_VAULT=E:\\Notes\nAUTRE_CLE_TEST=x\n")
        env = {k: v for k, v in os.environ.items() if k != "ALPHASIGNAL_VAULT"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(vault_chemin.dossier_vault(self.racine.name), os.path.abspath("E:\\Notes"))
            self.assertNotIn("AUTRE_CLE_TEST", os.environ)  # le .env n'est pas chargé

    def test_defaut_documents(self):
        env = {k: v for k, v in os.environ.items() if k != "ALPHASIGNAL_VAULT"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(vault_chemin.dossier_vault(self.racine.name), vault_chemin.VAULT_DEFAUT)
        self.assertTrue(vault_chemin.VAULT_DEFAUT.endswith(os.path.join("Documents", "AlphaSignalVault")))


if __name__ == "__main__":
    unittest.main()
