"""
tests/test_socle_hors_production.py — Le socle du futur dashboard reste hors de la production.

Règle posée à l'intégration (24/11/2026) : rien de ce que le socle ajoute n'est importé par un
cycle, par le moteur de décision ni par le dashboard actuel ; aucune décision de l'agent ne change.
1. aucun module de agents/, alerts/, dashboard/, utils/, ni config.py, ni un script autre que
   scripts/ledger_*.py, n'importe ledger, mesures ou importeurs (lecture du source, imports de
   tout niveau, y compris dans le corps des fonctions) ;
2. les trois paquets n'importent rien de l'agent (agents, alerts, config, dashboard, scripts, utils).
Le jour où le nouveau dashboard lira le grand livre, le point 1 sera à ouvrir pour lui, en
connaissance de cause.

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
        self.assertGreater(len(fichiers), 150)
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


if __name__ == "__main__":
    unittest.main()
