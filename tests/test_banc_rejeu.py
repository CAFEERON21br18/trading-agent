"""
tests/test_banc_rejeu.py — scripts/rejouer_chat.py : --noter sans réseau, --rejouer chez Groq
(appelant « banc », plafond, pause, arrêt propre, confirmation, consigne), et ask_llm hors
requête auditée n'écrit ni dans message_audit ni dans chat_history.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_banc_rejeu -v
Aucun appel réseau (ask_llm simulé ou fournisseurs simulés) ; valeurs inventées.
"""

import json
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

from scripts import rejouer_chat as rc
from scripts._banc_fichiers import journaux_detaches

LIMITE = {"text": None, "source": None, "error": "groq_ko:rate_limit_groq, gemini réservé",
          "tentatives": [{"fournisseur": "gemini", "statut": "réservé"},
                         {"fournisseur": "groq", "type_erreur": "rate_limit_groq"}]}


def ok(texte="Réponse inventée sur ACME.\n⚠️ Pas un conseil financier — paper trading.") -> dict:
    return {"text": texte, "source": "groq", "error": None, "tentatives": []}


class BaseBanc(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cas = os.path.join(self.dossier.name, "chat_cas")
        os.makedirs(self.cas)
        self.logs = journaux_detaches(self.cas)  # rien dans logs/ (production)
        self.logs.__enter__()

    def tearDown(self):
        self.logs.__exit__(None, None, None)
        self.dossier.cleanup()

    def ecrire(self, nom: str, origine="audit", reponse="ACME tient.", system="Consigne du cas.", prompt="P"):
        with open(os.path.join(self.cas, f"{nom}.json"), "w", encoding="utf-8") as f:
            json.dump({"question": "Q ?", "system": system, "prompt": prompt, "origine": origine,
                       "reponse_historique": reponse, "attendu": {"doit_contenir": ["ACME"],
                       "ne_doit_pas_contenir": [], "famille": "paper", "note": ""}}, f)


class TestNoter(BaseBanc):

    def test_seules_les_reponses_historiques_sont_notees(self):
        self.ecrire("1")
        self.ecrire("2", origine="audit_sans_llm", reponse="")
        self.ecrire("m_20260101_000000", origine="manuel", reponse="")
        with mock.patch("utils.llm.ask_llm", side_effect=AssertionError("aucun appel en --noter")):
            res = rc.noter_historique(self.cas)
        self.assertEqual(([r["cas"] for r in res["resultats"]], res["ignores_sans_reponse"]), (["1"], 2))
        self.assertEqual(res["resume"]["familles"]["paper"]["attendu_ok"], 1)


class TestRejouer(BaseBanc):

    def lancer(self, reponses, **kw) -> tuple:
        appel = mock.Mock(side_effect=reponses)
        pause = mock.Mock()
        res = rc.rejouer(self.cas, appel=appel, pause=pause, confirmer=lambda q: True, **kw)
        return res, appel, pause

    def test_appel_groq_banc_et_arret_propre(self):
        for i in range(1, 4):
            self.ecrire(str(i))
        res, appel, pause = self.lancer([ok(), LIMITE, ok()])
        self.assertEqual((res["arret"], res["envoyes"], res["prevus"]), ("rate_limit_groq", 2, 3))
        self.assertEqual(appel.call_count, 2)
        pause.assert_called_once_with(3.0)
        kw = appel.call_args.kwargs
        self.assertEqual((kw["appelant"], kw["max_tokens"], kw["mode"], kw["temperature"]),
                         ("banc", 900, "verbose", 0.6))
        from agents.chat._llm import SYSTEM_PROMPT
        self.assertEqual(kw["system"], SYSTEM_PROMPT)  # option (a) : consigne actuelle par défaut
        self.assertEqual((res["resultats"][1]["note"], res["resultats"][1]["erreur"]), (None, "rate_limit_groq"))
        self.assertEqual(res["resume"]["global"]["cas"], 1)

    def test_consigne_historique_ou_fichier(self):
        self.ecrire("1", system="Consigne du cas.")
        _, appel, _ = self.lancer([ok()], system_historique=True)
        self.assertEqual(appel.call_args.kwargs["system"], "Consigne du cas.")
        fichier = os.path.join(self.dossier.name, "essai.txt")
        with open(fichier, "w", encoding="utf-8") as f:
            f.write("Consigne à tester.")
        res, appel, _ = self.lancer([ok()], system_fichier=fichier)
        self.assertEqual((appel.call_args.kwargs["system"], res["consigne"]), ("Consigne à tester.", fichier))

    def test_plafond_de_30(self):
        for i in range(1, 32):
            self.ecrire(str(i))
        res, appel, _ = self.lancer([ok()] * 31, n_max=100)
        self.assertEqual((appel.call_count, res["prevus"]), (30, 30))

    def test_confirmation_au_dela_de_60000_jetons(self):
        self.ecrire("1", prompt="x" * 300_000)  # ≈ 75 000 jetons d'entrée
        appel = mock.Mock(side_effect=AssertionError("rien ne doit partir"))
        self.assertIsNone(rc.rejouer(self.cas, appel=appel, pause=mock.Mock(), confirmer=lambda q: False))
        entree, _ = rc.estimer_jetons([{"prompt": "x" * 400}], ["y" * 400])
        self.assertEqual(entree, 200)

    def test_refus_dans_une_requete_auditee(self):
        from utils.audit_trace import arreter_trace, demarrer_trace
        self.ecrire("1")
        _, jeton = demarrer_trace()
        try:
            with self.assertRaises(RuntimeError):
                self.lancer([ok()])
        finally:
            arreter_trace(jeton)


class TestAskLlmHorsAudit(BaseBanc):

    def test_aucune_ecriture_dans_message_audit_ni_chat_history(self):
        from utils import database, llm
        base = os.path.join(self.dossier.name, "t.db")
        conn = sqlite3.connect(base)
        conn.execute("CREATE TABLE message_audit (id INTEGER PRIMARY KEY, prompt_envoye TEXT)")
        conn.execute("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, message TEXT)")
        conn.commit()
        conn.close()
        with mock.patch.object(database, "DB_PATH", base), \
             mock.patch.object(llm, "_try_gemini", side_effect=AssertionError("Gemini réservé")), \
             mock.patch.object(llm, "_try_groq", return_value={"text": "ok", "error": None,
                                                               "retry_after_sec": None}):
            res = llm.ask_llm("P", system="S", mode="verbose", max_tokens=900, appelant="banc")
        self.assertEqual(res["source"], "groq")
        conn = sqlite3.connect(base)
        try:
            self.assertEqual([conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                              for t in ("message_audit", "chat_history")], [0, 0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
