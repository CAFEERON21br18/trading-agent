"""
tests/test_rejeu_isolement.py — Le rejeu appelle l'agent ; l'agent n'importe jamais le rejeu.

1. aucun module de agents/, alerts/, utils/, dashboard/ (hors dashboard/pro), ni config.py, ni un
   script autre que scripts/rejeu*.py, n'importe le paquet rejeu : aucun cycle, ni le moteur de
   décision, ni le paper trader ne peuvent en dépendre ;
2. les réglages de l'agent épinglés dans rejeu/parametres.py sont les valeurs par défaut écrites
   dans config.py (« ceux du code »), quel que soit le .env de la machine ;
3. data/rejeu/ et reports/rejeu/ sont hors git.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_isolement -v
Lecture de fichiers source seulement : aucune base, aucun réseau, aucun .env.
"""

import glob
import os
import re
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # même convention que les autres modules de test

from rejeu import parametres as P
from tests.test_socle_hors_production import _fichiers, imports_de

PRO = os.path.join(RACINE, "dashboard", "pro") + os.sep


class TestIsolement(unittest.TestCase):
    def test_l_agent_n_importe_pas_le_rejeu(self):
        fichiers = _fichiers("agents", "alerts", "dashboard", "utils", "scripts", "ledger", "mesures", "importeurs")
        fichiers += [os.path.join(RACINE, "config.py")]
        fichiers = [f for f in fichiers if not f.startswith(PRO)
                    and not (os.path.basename(os.path.dirname(f)) == "scripts"
                             and os.path.basename(f).startswith("rejeu"))]
        self.assertGreater(len(fichiers), 180)
        for chemin in fichiers:
            with self.subTest(fichier=os.path.relpath(chemin, RACINE)):
                self.assertEqual(imports_de(chemin, {"rejeu"}), [])
        cycles = glob.glob(os.path.join(RACINE, "scripts", "cycle_*.py"))
        self.assertGreaterEqual(len(cycles), 5)
        self.assertTrue(all(c in fichiers for c in cycles))

    def test_reglages_epingles_aux_valeurs_par_defaut_du_code(self):
        with open(os.path.join(RACINE, "config.py"), encoding="utf-8") as f:
            source = f.read()

        def defaut(nom):
            return float(re.search(rf'_get_optional\("{nom}", "(-?[0-9.]+)"\)', source).group(1))
        for nom, valeur in P.CONFIG_AGENT.items():
            with self.subTest(reglage=nom):
                self.assertEqual(defaut(nom), float(valeur))
        self.assertEqual((defaut("SEUIL_BUY"), defaut("SEUIL_SELL")), (P.SEUIL_BUY, P.SEUIL_SELL))
        self.assertEqual(defaut("CAPITAL"), P.CAPITAL_DU_CODE)
        self.assertEqual(defaut("CAPITAL_STOP_THRESHOLD"), P.PART_SEUIL_ARRET * P.CAPITAL_DU_CODE)

    def test_critere_et_parametres_de_mesure(self):
        with open(os.path.join(RACINE, "docs", "REGISTRE_CRITERES.md"), encoding="utf-8") as f:
            registre = " ".join(f.read().split())
        section = registre[registre.index("## 10. Rejeu sur plusieurs années du cœur technique"):]
        for attendu in ("capital de 1 000 €, profil de frais « Revolut »", "années civiles complètes de 2018 à 2025",
                        "bootstrap, 10 000 tirages, graine fixe", "au moins 4 des 8 années",
                        "Moins de 100 trades clos"):
            self.assertIn(attendu, section)
        self.assertEqual((P.CONFIG_QUI_DECIDE, P.ANNEES, P.TIRAGES, P.MIN_TRADES, P.CONFIANCE),
                         ((1000, "revolut"), tuple(range(2018, 2026)), 10_000, 100, 0.95))
        self.assertEqual((P.CAPITAUX, sorted(P.PROFILS)), ((100, 1000, 10000), ["cfd", "revolut"]))
        self.assertEqual((str(P.PROFILS["revolut"]["par_ordre"]), str(P.PROFILS["cfd"]["ecart"]["action"]),
                          str(P.PROFILS["cfd"]["ecart"]["crypto"]), str(P.PROFILS["cfd"]["financement_par_nuit"])),
                         ("1", "0.0010", "0.0050", "0.0002"))

    def test_sorties_du_rejeu_hors_git(self):
        for chemin in (os.path.join("data", "rejeu", "ledger_rejeu.db"), os.path.join("data", "rejeu", "lancement.json"),
                       os.path.join("data", "rejeu", "barres", "AAPL.csv"), os.path.join("reports", "rejeu", "RAPPORT.md")):
            sortie = subprocess.run(["git", "check-ignore", "-q", chemin], cwd=RACINE)
            self.assertEqual(sortie.returncode, 0, chemin)
        self.assertTrue(os.path.normcase(P.DOSSIER).endswith(os.path.normcase(os.path.join("data", "rejeu"))))


if __name__ == "__main__":
    unittest.main()
