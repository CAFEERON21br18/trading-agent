"""
tests/test_banc_export.py — Export des cas du banc de rejeu (scripts/chat_cas_export.py) :
lecture seule de message_audit, origines, séparation [SYSTEM] / [PROMPT], aucun fichier réécrit,
cas manuels.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_banc_export -v
Base et dossier temporaires ; messages 100 % inventés.
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

from scripts import chat_cas_export as ex
from scripts._banc_fichiers import ecrire_resultats, lister_cas

SYSTEM = "Consigne inventée.\nRègle 1.\n"


def envoye(prompt: str) -> str:
    return f"[SYSTEM]\n{SYSTEM}\n\n[PROMPT]\n{prompt}"  # format d'agents/chat/_audit_record.py


class TestExport(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cas = os.path.join(self.dossier.name, "chat_cas")
        self.base = os.path.join(self.dossier.name, "t.db")
        conn = sqlite3.connect(self.base)
        conn.execute("CREATE TABLE message_audit (id INTEGER PRIMARY KEY, timestamp TEXT, "
                     "message_utilisateur TEXT, llm_utilise TEXT, prompt_envoye TEXT, reponse_brute TEXT)")
        conn.executemany("INSERT INTO message_audit VALUES (?, ?, ?, ?, ?, ?)", [
            (1, "2026-01-01T10:00:00+00:00", "Question A ?", "groq", envoye("Prompt A"), "Réponse A"),
            (2, "2026-01-01T10:05:00+00:00", "Question B ?", "rule_based", envoye("Prompt B"), "Bandeau B"),
            (3, "2026-01-01T10:10:00+00:00", "Question C ?", "rule_based", None, "Bandeau C"),
            (4, "2026-01-01T10:15:00+00:00", "Question D ?", "gemini", None, "Réponse D"),
            (26, "2026-01-02T15:36:00+00:00", "Question E ?", "gemini", envoye("Prompt E"), "Réponse E"),
        ])
        conn.commit()
        conn.close()

    def tearDown(self):
        self.dossier.cleanup()

    def lire(self, nom: str) -> dict:
        with open(os.path.join(self.cas, nom), encoding="utf-8") as f:
            return json.load(f)

    def test_export_origines_et_separation(self):
        self.assertEqual(ex.exporter(self.base, self.cas), {"audit": 2, "audit_sans_llm": 1, "deja_presents": 0})
        self.assertEqual(sorted(os.listdir(self.cas)), ["1.json", "2.json", "26.json"])
        a = self.lire("1.json")
        self.assertEqual((a["system"], a["prompt"], a["question"]), (SYSTEM, "Prompt A", "Question A ?"))
        self.assertEqual((a["origine"], a["reponse_historique"], a["llm_historique"]), ("audit", "Réponse A", "groq"))
        self.assertEqual(a["attendu"], {"doit_contenir": [], "ne_doit_pas_contenir": [], "famille": "", "note": ""})
        b = self.lire("2.json")
        self.assertEqual((b["origine"], b["reponse_historique"], b["prompt"]), ("audit_sans_llm", "", "Prompt B"))
        self.assertEqual(self.lire("26.json")["attendu"]["note"], "essai 08/10")

    def test_lecture_seule_de_la_base(self):
        avant = os.path.getmtime(self.base), os.path.getsize(self.base)
        ex.exporter(self.base, self.cas)
        self.assertEqual((os.path.getmtime(self.base), os.path.getsize(self.base)), avant)

    def test_jamais_de_reecriture(self):
        ex.exporter(self.base, self.cas)
        chemin = os.path.join(self.cas, "1.json")
        cas = self.lire("1.json")
        cas["attendu"]["doit_contenir"] = ["rempli à la main"]
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(cas, f)
        self.assertEqual(ex.exporter(self.base, self.cas), {"audit": 0, "audit_sans_llm": 0, "deja_presents": 3})
        self.assertEqual(self.lire("1.json")["attendu"]["doit_contenir"], ["rempli à la main"])

    def test_separer_sans_marqueur(self):
        self.assertEqual(ex.separer("texte brut"), ("", "texte brut"))
        self.assertEqual(ex.separer(None), ("", ""))

    def test_cas_manuel(self):
        construit = {"intention": "advice_buy", "system": SYSTEM, "prompt": "Prompt M",
                     "sources_coupees": ["alpha_vantage"]}
        with mock.patch("scripts._chat_a_blanc.construire_cas", return_value=construit) as cc:
            c1, cas = ex.nouveau("Question M ?", self.cas)
            c2, _ = ex.nouveau("Question M ?", self.cas)  # même seconde : nouveau nom, rien d'écrasé
        cc.assert_called_with("Question M ?", self.cas)
        self.assertNotEqual(c1, c2)
        self.assertTrue(os.path.basename(c1).startswith("m_"))
        self.assertEqual((cas["origine"], cas["reponse_historique"], cas["sources_coupees"]),
                         ("manuel", "", ["alpha_vantage"]))
        self.assertEqual([c["_id"] for c in lister_cas(self.cas)][0][:2], "m_")

    def test_ordre_des_cas_et_resultats(self):
        ex.exporter(self.base, self.cas)
        self.assertEqual([c["_id"] for c in lister_cas(self.cas)], ["1", "2", "26"])  # numérique, pas texte
        chemin = ecrire_resultats(self.cas, "noter", {"x": 1})
        self.assertEqual(os.path.dirname(chemin), os.path.join(self.cas, "resultats"))
        self.assertEqual([c["_id"] for c in lister_cas(self.cas)], ["1", "2", "26"])  # resultats/ ignoré


if __name__ == "__main__":
    unittest.main()
