"""
tests/test_banc_reconstruire.py — --reconstruire du banc (scripts/_banc_rejeu.py, rejouer_chat.py) :
cas manuels seulement, historique_simule et CHAT_HISTORIQUE transmis, rappel du contexte du jour,
avertissement de --comparer, options de la ligne de commande.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_banc_reconstruire -v
Aucun appel réseau (construction et ask_llm simulées) ; valeurs inventées.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

from scripts import _banc_rejeu as br, rejouer_chat as rc
from scripts._banc_fichiers import journaux_detaches

HISTO = [{"role": "user", "texte": "Que penses-tu de ACME ?", "il_y_a_min": 5},
         {"role": "assistant", "texte": "ACME : HOLD.", "il_y_a_min": 5}]
BLOCS = "**Les faits** : ACME en HOLD.\n**Ma lecture** : attendre.\n**Ce qui manque** : rien"


class TestReconstruire(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cas = self.dossier.name
        self.logs = journaux_detaches(self.cas)  # rien dans logs/ (production)
        self.logs.__enter__()
        for nom, cas in (("1", {"origine": "audit", "question": "Q audit ?", "prompt": "P"}),
                         ("m_1", {"origine": "manuel", "question": "Et lui ?", "historique_simule": HISTO}),
                         ("m_2", {"origine": "manuel", "question": "Comment va le paper ?"})):
            with open(os.path.join(self.cas, f"{nom}.json"), "w", encoding="utf-8") as f:
                json.dump({**cas, "attendu": {"famille": "suivi"}}, f)
        self.appels_construire = []

    def tearDown(self):
        self.logs.__exit__(None, None, None)
        self.dossier.cleanup()

    def construire(self, question, dossier, historique_simule=None, chat_historique=None):
        self.appels_construire.append((question, historique_simule, chat_historique))
        return {"intention": "paper_status", "system": "Consigne actuelle.", "sources_coupees": ["alpha_vantage"],
                "prompt": f"INTENTION DÉTECTÉE : paper_status\n\nQuestion : {question}",
                "tickers_herites": question == "Et lui ?", "messages_historique": len(historique_simule or [])}

    def lancer(self, historique: bool, **kw) -> tuple:
        appel = mock.Mock(return_value={"text": BLOCS, "source": "groq", "tentatives": []})
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            res = br.reconstruire(self.cas, historique, appel=appel, pause=mock.Mock(),
                                  confirmer=lambda q: True, construire=self.construire, **kw)
        return res, appel, sortie.getvalue()

    def test_cas_manuels_seulement_historique_et_interrupteur_transmis(self):
        res, appel, sortie = self.lancer(True)
        self.assertEqual(self.appels_construire, [("Et lui ?", HISTO, True), ("Comment va le paper ?", [], True)])
        self.assertEqual((res["mode"], res["historique"], res["envoyes"]), ("reconstruire", "on", 2))
        self.assertTrue(res["jour"])
        self.assertIn("Ne comparer que deux --reconstruire lancés le même jour", sortie)
        self.assertEqual(appel.call_args.kwargs["system"], "Consigne actuelle.")
        r = res["resultats"][0]
        self.assertEqual((r["cas"], r["tickers_herites"], r["messages_historique"], r["sources_coupees"]),
                         ("m_1", True, 2, ["alpha_vantage"]))
        self.assertIs(r["note"]["trois_blocs_ok"], True)  # noté sur le prompt reconstruit

    def test_historique_off_et_consigne_fichier(self):
        fichier = os.path.join(self.cas, "v2.txt.tmp")
        with open(fichier, "w", encoding="utf-8") as f:
            f.write("Consigne à tester.")
        res, appel, _ = self.lancer(False, system_fichier=fichier)
        self.assertEqual({c[2] for c in self.appels_construire}, {False})
        self.assertEqual((res["historique"], appel.call_args.kwargs["system"]), ("off", "Consigne à tester."))


class TestComparaisonEtOptions(unittest.TestCase):

    def test_avertissement_de_comparaison(self):
        rec_a = {"mode": "reconstruire", "jour": "2026-11-02"}
        self.assertIsNone(br.avertissement_comparaison(rec_a, {"mode": "reconstruire", "jour": "2026-11-02"}))
        self.assertIn("deux jours différents",
                      br.avertissement_comparaison(rec_a, {"mode": "reconstruire", "jour": "2026-11-03"}))
        self.assertIn("autre mode", br.avertissement_comparaison(rec_a, {"mode": "noter"}))
        self.assertIsNone(br.avertissement_comparaison({"mode": "rejouer"}, {"mode": "noter"}))

    def test_options_de_la_ligne_de_commande(self):
        for argv in (["--reconstruire"], ["--historique", "on"],
                     ["--reconstruire", "--historique", "on", "--system-historique"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                rc.main(argv)

    def test_comparer_affiche_l_avertissement(self):
        with tempfile.TemporaryDirectory() as d:
            fichiers = []
            for nom, contenu in (("a", {"mode": "reconstruire", "jour": "2026-11-02"}), ("b", {"mode": "noter"})):
                chemin = os.path.join(d, f"{nom}.json")
                with open(chemin, "w", encoding="utf-8") as f:
                    json.dump({**contenu, "resultats": [], "resume": {"global": {}, "familles": {}}}, f)
                fichiers.append(chemin)
            sortie = io.StringIO()
            with redirect_stdout(sortie):
                self.assertEqual(rc.main(["--comparer", *fichiers]), 0)
        self.assertIn("non interprétable", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
