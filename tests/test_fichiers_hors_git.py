"""
tests/test_fichiers_hors_git.py — fichiers écrits en production hors du suivi git (dépôt public).

1. .gitignore couvre reports/, package-lock.json et les fichiers d'état de data/ écrits par le code
   (compteur NewsAPI du rapport, état de la surveillance du dashboard, copies de la base) ;
2. les chemins réellement écrits par ces modules tombent sous une règle du .gitignore ;
3. premier lancement : les rapports quotidiens recréent reports/daily/ s'il est absent.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_fichiers_hors_git -v
Dossier temporaire ; aucun fichier de reports/ ni de data/ n'est lu ni écrit.
"""

import fnmatch
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


def _regles() -> list[str]:
    with open(os.path.join(RACINE, ".gitignore"), encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def _ignore(chemin_absolu: str) -> bool:
    """Version réduite des règles de .gitignore : dossier « x/ » (préfixe), motif ou nom exact."""
    rel = os.path.relpath(chemin_absolu, RACINE).replace(os.sep, "/")
    for r in _regles():
        if r.endswith("/") and (rel + "/").startswith(r):
            return True
        if fnmatch.fnmatch(rel, r) or fnmatch.fnmatch(os.path.basename(rel), r):
            return True
    return False


class TestRegles(unittest.TestCase):
    def test_entrees_presentes(self):
        regles = set(_regles())
        for e in ("reports/", "package-lock.json", "data/rapport_newsapi.json",
                  "data/surveillance_dashboard.json", "data/sauvegardes/"):
            self.assertIn(e, regles)

    def test_chemins_ecrits_par_le_code(self):
        from agents import report_sections
        from scripts import migrer_devise_reelle, purger_signaux_demo, surveiller_dashboard
        from utils import helpers
        chemins = [report_sections.COMPTEUR, surveiller_dashboard.ETAT,
                   os.path.join(migrer_devise_reelle.SAUVEGARDES_DEFAUT, "copie.db"),
                   os.path.join(purger_signaux_demo.DOSSIER_SAUVEGARDES, "copie.json"),
                   os.path.join(helpers.BASE_DIR, "reports", "daily", "report_2026-01-01.md"),
                   os.path.join(helpers.BASE_DIR, "reports", "weekly", "week_2026_W01.md"),
                   os.path.join(RACINE, "package-lock.json")]
        for c in chemins:
            self.assertTrue(_ignore(c), c)

    def test_watchlist_reste_suivie(self):
        # data/watchlist.json sert de configuration au premier lancement : elle reste versionnée
        self.assertFalse(_ignore(os.path.join(RACINE, "data", "watchlist.json")))


class TestPremierLancement(unittest.TestCase):
    def test_rapport_recree_le_dossier(self):
        from utils import helpers
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(helpers, "BASE_DIR", tmp):
            chemin = helpers.sauvegarder_rapport("# Rapport de test\n")
            self.assertTrue(os.path.isfile(chemin))
            self.assertEqual(os.path.dirname(chemin), os.path.join(tmp, "reports", "daily"))


if __name__ == "__main__":
    unittest.main()
