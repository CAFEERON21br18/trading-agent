"""
tests/test_memoire_hors_git.py — memory/ hors du suivi git (TODO §39).

1. Les 6 fichiers écrits par les cycles sont dans .gitignore ; les modèles memory/<nom>.md.exemple
   des fichiers enrichis par ajout existent et ne contiennent aucune entrée ;
2. premier lancement : chaque lecteur fonctionne quand les fichiers sont absents (mémoire du Decision
   Engine, tracker d'intuition, dashboard, vault) ;
3. chaque écrivain par ajout recrée le fichier absent depuis son modèle (en-tête et sections gardés),
   et ne touche jamais un fichier présent.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_memoire_hors_git -v
Dossiers temporaires ; aucun fichier de memory/ n'est lu ni écrit.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import memoire_modeles

ECRITS = ("intuition_log.md", "lessons_learned.md", "market_patterns.md", "metacognition_log.md",
          "performance_tracker.md", "trade_journal.md")
MODELES = {"intuition_log.md": "### ", "lessons_learned.md": "`20", "market_patterns.md": "PATTERN-",
           "trade_journal.md": "### SIG-"}  # nom -> marque d'une entrée, absente du modèle


class TestSuivi(unittest.TestCase):
    def test_gitignore_et_modeles(self):
        with open(os.path.join(RACINE, ".gitignore"), encoding="utf-8") as f:
            ignores = {l.strip() for l in f}
        for nom in ECRITS:
            self.assertIn(f"memory/{nom}", ignores)
        for nom, entree in MODELES.items():
            with open(os.path.join(RACINE, "memory", nom + ".exemple"), encoding="utf-8") as f:
                modele = f.read()
            self.assertTrue(modele.startswith("# AlphaSignal"), nom)
            self.assertNotIn(entree, modele, nom)


class TestPremierLancement(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        self.vide = os.path.join(self.d.name, "memory")  # n'existe pas encore

    def test_lecteurs_sans_fichiers(self):
        from agents import memory_reader
        from agents.trade_journalist import intuition_tracker
        from agents.vault.notes_positions import entrees_intuition
        import config
        from dashboard.api import queries
        with mock.patch.object(memory_reader, "MEMORY_DIR", self.vide):
            self.assertIsNone(memory_reader.lire_winrate_par_actif("AAA"))
            self.assertEqual((memory_reader.chercher_lecons("AAA"), memory_reader.chercher_patterns("AAA")), ([], []))
            self.assertIsInstance(memory_reader.consulter_memoire("AAA"), dict)
        with mock.patch.object(intuition_tracker, "INTUITION_LOG", os.path.join(self.vide, "intuition_log.md")):
            self.assertEqual(intuition_tracker.stats_intuition()["total"], 0)
            self.assertEqual(intuition_tracker.synchroniser_intuition(), {"completees": 0, "tickers": []})
        with mock.patch.object(config, "MEMORY_DIR", self.vide):
            self.assertEqual(queries.fichier_memoire("market_patterns.md"), "")
        self.assertEqual(entrees_intuition(""), [])
        self.assertFalse(os.path.exists(self.vide))  # aucun lecteur n'a rien créé

    def test_ecrivains_recreent_depuis_le_modele(self):
        from agents import intuition
        from agents.trade_journalist import journalist, learner
        chemins = {n: os.path.join(self.vide, n) for n in MODELES}
        self.assertTrue(learner._ajouter_si_nouveau(chemins["market_patterns.md"], "M-1", "entrée inventée M-1"))
        self.assertTrue(learner._ajouter_si_nouveau(chemins["lessons_learned.md"], "L-1", "leçon inventée L-1"))
        with mock.patch.object(journalist, "JOURNAL_FILE", chemins["trade_journal.md"]):
            journalist.ajouter_au_journal_md("SIG-9999", "AAA", "LONG", 7, 10.0, 9.0, 11.0, 12.0,
                                             "Decision Engine", "raison inventée", "2026-10-19T08:00:00+00:00")
        with mock.patch.object(intuition, "INTUITION_LOG", chemins["intuition_log.md"]):
            intuition.enregistrer_decision_intuitive("AAA", {"decision": "BUY", "confidence": 7, "score_composite": 1.0},
                                                     {"ajustement": 1, "pressentiment": "neutre", "raisons": ["r"]})
        for nom, chemin in chemins.items():
            with open(os.path.join(RACINE, "memory", nom + ".exemple"), encoding="utf-8") as f:
                modele = f.read()
            with open(chemin, encoding="utf-8") as f:
                ecrit = f.read()
            self.assertTrue(ecrit.startswith(modele), nom)  # en-tête et sections du modèle
            self.assertGreater(len(ecrit), len(modele), nom)  # puis l'entrée ajoutée
        with open(chemins["intuition_log.md"], encoding="utf-8") as f:
            self.assertIn("## Statistiques d'intuition", f.read())  # section que met à jour intuition_tracker

    def test_fichier_present_jamais_touche(self):
        os.makedirs(self.vide)
        chemin = os.path.join(self.vide, "trade_journal.md")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("contenu existant\n")
        memoire_modeles.preparer(chemin)
        memoire_modeles.preparer(os.path.join(self.vide, "sans_modele.md"))
        with open(chemin, encoding="utf-8") as f:
            self.assertEqual(f.read(), "contenu existant\n")
        self.assertFalse(os.path.exists(os.path.join(self.vide, "sans_modele.md")))


if __name__ == "__main__":
    unittest.main()
