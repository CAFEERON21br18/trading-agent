"""
tests/test_chat_a_blanc.py — Mode à blanc du banc de rejeu (scripts/_chat_a_blanc.py) :
copie jetable supprimée même en cas d'erreur, aucune écriture en production, Alpha Vantage
coupé, logs détournés, et prompt identique à celui du vrai chat (même blocage des deux côtés).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_chat_a_blanc -v
Bases et dossiers temporaires, réseau coupé, valeurs inventées.
"""

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

from utils import cache, database
from utils.logger import get_logger
from scripts import _chat_a_blanc as ab
from scripts._banc_fichiers import journaux_detaches


class BaseABlanc(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cas = os.path.join(self.dossier.name, "chat_cas")
        self.base = os.path.join(self.dossier.name, "prod.db")
        conn = sqlite3.connect(self.base)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        self.patchs = [mock.patch.object(database, "DB_PATH", self.base),
                       mock.patch.object(cache, "CACHE_DIR", os.path.join(self.dossier.name, "cache"))]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def tmp(self) -> list:
        return os.listdir(os.path.join(self.cas, "tmp"))


class TestABlanc(BaseABlanc):

    def test_copie_jetable_supprimee_meme_en_cas_d_erreur(self):
        with self.assertRaises(RuntimeError):
            with ab.a_blanc(self.cas) as etat:
                self.assertEqual(os.path.dirname(etat["copie"]), os.path.join(self.cas, "tmp"))
                self.assertTrue(os.path.exists(etat["copie"]))
                database.get_connection().close()  # une vraie connexion, comme le chemin du chat
                raise RuntimeError("panne au milieu")
        self.assertEqual(self.tmp(), [])
        with ab.a_blanc(self.cas) as etat:
            pass
        self.assertEqual(self.tmp(), [])

    def test_ecriture_sql_dans_la_copie_detectee_production_intacte(self):
        avant = ab.empreinte(self.base)
        with ab.a_blanc(self.cas) as etat:
            conn = database.get_connection()
            conn.execute("INSERT INTO t VALUES (2)")
            conn.commit()
            conn.close()
        self.assertEqual(etat["ecritures_sql"], ["t"])
        self.assertEqual(ab.empreinte(self.base), avant)
        self.assertEqual(self.tmp(), [])

    def test_construire_cas_refuse_le_cas_si_ecriture(self):
        def chemin_qui_ecrit(question):
            conn = database.get_connection()
            conn.execute("INSERT INTO t VALUES (3)")
            conn.commit()
            conn.close()
            return {"intention": "general", "system": "s", "prompt": "p"}
        with mock.patch.object(ab, "construire_prompt", chemin_qui_ecrit):
            with self.assertRaises(RuntimeError):
                ab.construire_cas("question inventée", self.cas)
        self.assertEqual(self.tmp(), [])

    def test_cache_alpha_vantage_open_et_logs(self):
        from agents.analysts.fundamental_analyst import alphavantage
        with mock.patch.object(alphavantage.requests, "get", side_effect=AssertionError("réseau")), \
             ab.a_blanc(self.cas) as etat:
            self.assertIs(cache.ecrire("news", "ACME_5", {"x": 1}), False)
            self.assertEqual(alphavantage.recuperer_overview("ACME"), {})
            with self.assertRaises(PermissionError):
                open(os.path.join(RACINE, "memory", "jamais_ecrit_par_le_banc.md"), "a")
            with open(os.path.join(self.cas, "autorise.txt"), "w") as f:
                f.write("ok")
            journal = get_logger("tests.banc.a_blanc")
            journal.warning("message du banc")
            prod = {os.path.normcase(p) for p in (os.path.join(RACINE, "logs", "alphasignal.log"),
                                                  os.path.join(RACINE, "logs", "errors.log"))}
            self.assertFalse(any(os.path.normcase(getattr(h, "baseFilename", "")) in prod
                                 for h in journal.handlers))
        self.assertEqual(etat["sources_coupees"], {"alpha_vantage"})
        self.assertFalse(os.path.exists(os.path.join(self.dossier.name, "cache", "news")))
        with open(os.path.join(self.cas, "banc.log"), encoding="utf-8") as f:
            self.assertIn("message du banc", f.read())


class TestFidelite(BaseABlanc):
    """Le prompt construit à blanc est celui que le vrai chat enverrait à ask_llm."""

    def setUp(self):
        super().setUp()
        from utils.portfolio_db import initialiser_paper_db
        with journaux_detaches(self.cas):  # rien dans logs/ (production)
            database.initialiser_base()
            initialiser_paper_db()
        from agents import asset_analyzer
        from agents.analysts.sentiment_analyst import analyst
        from agents.chat import context_builder
        hors_ligne = [
            mock.patch.object(asset_analyzer, "recuperer_news", return_value=[]),
            mock.patch.object(analyst, "recuperer_fear_greed_crypto",
                              return_value={"valeur": 55, "label": "Neutral"}),
            mock.patch.object(context_builder, "_heure_locale", return_value="12h00"),
            mock.patch("requests.sessions.Session.request", side_effect=RuntimeError("réseau coupé")),
        ]
        for p in hors_ligne:
            p.start()
        self.patchs += hors_ligne

    def _prompt_du_chat(self, question: str) -> dict:
        """chat_engine.repondre sans le décorateur d'audit ; ask_llm intercepté ; même
        blocage d'Alpha Vantage que le mode à blanc."""
        from agents.analysts.fundamental_analyst import alphavantage
        from agents.chat import _llm, chat_engine
        vu = {}

        def ask_llm(prompt, system=None, **kw):
            vu.update(prompt=prompt, system=system)
            return {"text": "réponse simulée suffisamment longue pour être gardée", "source": "groq"}
        coupe = ab._alpha_vantage_coupe({"sources_coupees": set()})
        with journaux_detaches(self.cas), \
             mock.patch.object(alphavantage, "_appel_av", coupe), \
             mock.patch.object(_llm, "llm_disponible", return_value={"gemini": True, "groq": True}), \
             mock.patch.object(_llm, "ask_llm", ask_llm):
            chat_engine.repondre.__wrapped__(question)
        return vu

    def test_meme_prompt_que_le_chat(self):
        for question, coupees in (("Faut-il acheter NVDA ?", ["alpha_vantage"]),
                                  ("Comment se porte le paper ?", [])):
            with self.subTest(question=question):
                cas = ab.construire_cas(question, self.cas)
                chat = self._prompt_du_chat(question)
                self.assertEqual((cas["system"], cas["prompt"]), (chat["system"], chat["prompt"]))
                self.assertEqual(cas["sources_coupees"], coupees)
                self.assertIn(question, cas["prompt"])
        self.assertEqual(self.tmp(), [])


if __name__ == "__main__":
    unittest.main()
