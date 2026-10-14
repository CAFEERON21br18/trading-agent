"""
tests/test_real_devise_gabarits.py — D1 : gabarits real.html et plans.html. Montants des positions
dans leur devise (« $ »), « € » seulement pour le capital et les budgets des plans ; chiffres qui
mélangent les deux marqués « non converti » ; saisie dans la devise de cotation.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_real_devise_gabarits -v
Lecture des gabarits seulement : ni base, ni réseau, ni logs.
"""

import os
import unittest

GABARITS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "templates")


def lire(nom: str) -> str:
    with open(os.path.join(GABARITS, nom), encoding="utf-8") as f:
        return f.read()


def lignes_en_euros(nom: str) -> list[str]:
    """Lignes avec « € », hors commentaires et table des symboles."""
    return [l.strip() for l in lire(nom).splitlines() if "€" in l and not l.strip().startswith("//")
            and not l.strip().startswith("const SYMBOLES")]


class TestGabarits(unittest.TestCase):
    def test_euros_seulement_sur_le_capital_et_les_budgets(self):
        self.assertTrue(lignes_en_euros("real.html"))
        for l in lignes_en_euros("real.html"):
            self.assertIn("apital", l)
        for l in lignes_en_euros("plans.html"):
            self.assertTrue("Budget" in l or "Montant cible" in l, l)

    def test_chiffres_mixtes_marques_non_convertis(self):
        real, plans = lire("real.html"), lire("plans.html")
        self.assertIn("${b.available.toFixed(2)} (non converti)", real)
        self.assertIn("(${pctInv}%, non converti)", real)
        self.assertEqual(plans.count("non converti"), 4)  # carte (2) et détail (2) d'un plan

    def test_saisie_dans_la_devise_de_cotation(self):
        real = lire("real.html")
        self.assertEqual(real.count('placeholder="Montant (devise de cotation, $ pour les actions US)"'), 2)
        self.assertIn("(${sym(devise)}, devise de cotation)", real)  # invite de calibration
        self.assertIn("Prix de sortie (${s}, devise de la position)", real)


if __name__ == "__main__":
    unittest.main()
