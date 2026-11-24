"""
tests/test_socle_hors_production.py — Le socle du futur dashboard reste hors de la production.

Règle posée à l'intégration (24/11/2026) : rien de ce que le socle ajoute n'est importé par un
cycle, par le moteur de décision ni par le dashboard actuel ; aucune décision de l'agent ne change.
1. aucun module de agents/, alerts/, dashboard/, utils/, ni config.py, ni un script autre que
   scripts/ledger_*.py, n'importe ledger, mesures ou importeurs (lecture du source, imports de
   tout niveau, y compris dans le corps des fonctions) ;
2. les trois paquets n'importent rien de l'agent (agents, alerts, config, dashboard, scripts, utils).
Ouvert le 24/11/2026 pour le dashboard professionnel, et pour lui seul (consigne des pages
« Vue d'ensemble » et « Mes trades ») : dashboard/pro/ lit le grand livre. En échange :
3. dashboard/pro n'est importé que par dashboard/app.py et par lui-même : ni un cycle, ni le
   moteur de décision, ni le paper trader n'atteignent le socle par ce chemin ;
4. rien du portefeuille fantôme Jev dans dashboard/pro ni dans ses gabarits.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_socle_hors_production -v
Lecture de fichiers source seulement : aucune base, aucun réseau, aucun .env.
"""

import ast
import glob
import os
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # même convention que les autres modules de test

SOCLE = {"ledger", "mesures", "importeurs"}
AGENT = {"agents", "alerts", "config", "dashboard", "scripts", "utils"}
PRO = os.path.join(RACINE, "dashboard", "pro") + os.sep  # seul paquet de l'agent ouvert au socle


def _fichiers(*dossiers: str) -> list[str]:
    trouves = []
    for d in dossiers:
        trouves += glob.glob(os.path.join(RACINE, d, "**", "*.py"), recursive=True)
    return sorted(f for f in trouves if "__pycache__" not in f)


def imports_de(chemin: str, paquets: set[str]) -> list[tuple[int, str]]:
    """(ligne, module) des imports absolus du fichier qui visent l'un des paquets."""
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read())
    trouves = []
    for n in ast.walk(arbre):
        noms = ([a.name for a in n.names] if isinstance(n, ast.Import)
                else [n.module or ""] if isinstance(n, ast.ImportFrom) and not n.level else [])
        trouves += [(n.lineno, nom) for nom in noms if nom.split(".")[0] in paquets]
    return trouves


class TestSocleHorsProduction(unittest.TestCase):
    def test_la_production_n_importe_pas_le_socle(self):
        fichiers = _fichiers("agents", "alerts", "dashboard", "utils", "scripts") + [os.path.join(RACINE, "config.py")]
        fichiers = [f for f in fichiers if not os.path.basename(f).startswith("ledger_")
                    or os.path.basename(os.path.dirname(f)) != "scripts"]
        fichiers = [f for f in fichiers if not f.startswith(PRO)]
        self.assertGreater(len(fichiers), 150)
        self.assertIn(os.path.join(RACINE, "dashboard", "app.py"), fichiers)  # l'application reste fermée
        for chemin in fichiers:
            with self.subTest(fichier=os.path.relpath(chemin, RACINE)):
                self.assertEqual(imports_de(chemin, SOCLE), [])

    def test_le_socle_n_importe_pas_l_agent(self):
        fichiers = _fichiers(*sorted(SOCLE))
        self.assertGreaterEqual(len(fichiers), 12)
        for chemin in fichiers:
            with self.subTest(fichier=os.path.relpath(chemin, RACINE)):
                self.assertEqual(imports_de(chemin, AGENT), [])

    def test_detecte_un_import(self):
        chemin = os.path.join(RACINE, "scripts", "ledger_sync_paper.py")
        self.assertEqual({nom for _, nom in imports_de(chemin, SOCLE)}, {"ledger", "importeurs"})
        chemin = os.path.join(RACINE, "dashboard", "pro", "donnees.py")
        self.assertEqual({nom for _, nom in imports_de(chemin, SOCLE)}, {"ledger", "mesures"})

    def test_dashboard_pro_importe_par_l_application_seule(self):
        fichiers = _fichiers("agents", "alerts", "dashboard", "utils", "scripts") + [os.path.join(RACINE, "config.py")]
        importeurs = {os.path.relpath(f, RACINE).replace(os.sep, "/") for f in fichiers
                      if not f.startswith(PRO)
                      and any(nom.startswith("dashboard.pro") for _, nom in imports_de(f, {"dashboard"}))}
        self.assertLessEqual(importeurs, {"dashboard/app.py"})

    def test_dashboard_pro_sans_jev(self):
        gabarits = glob.glob(os.path.join(RACINE, "dashboard", "templates", "pro*.html"))
        fichiers = _fichiers(os.path.join("dashboard", "pro")) + gabarits
        self.assertGreaterEqual(len(fichiers), 4)
        for chemin in fichiers:
            with self.subTest(fichier=os.path.relpath(chemin, RACINE)), open(chemin, encoding="utf-8") as f:
                texte = f.read().lower()
                # seule mention permise : la phrase qui dit que le fantôme n'est ni lu ni affiché
                self.assertNotIn("jev", texte.replace("fantôme jev n'est ni lu", ""))


if __name__ == "__main__":
    unittest.main()
