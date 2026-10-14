"""
tests/test_real_devise_gabarits.py — D1 : gabarits real.html et plans.html. Montants des positions
dans leur devise (« $ »), « € » seulement pour le capital, les budgets des plans et les valeurs
converties (taux affiché à côté, « non disponible » sans taux) ; saisie dans la devise de cotation.

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
    def test_euros_seulement_sur_le_capital_les_budgets_et_les_valeurs_converties(self):
        self.assertTrue(lignes_en_euros("real.html"))
        for l in lignes_en_euros("real.html"):
            self.assertTrue("apital" in l or "enEur" in l, l)
        for l in lignes_en_euros("plans.html"):
            self.assertTrue("Budget" in l or "Montant cible" in l or "pnl_total_eur" in l, l)

    def test_resultats_convertis_avec_le_taux_affiche(self):
        real, plans = lire("real.html"), lire("plans.html")
        for t in (real, plans):
            self.assertNotIn("non converti", t)
        self.assertIn("${enEur(b.available)}", real)
        self.assertIn("${escHtml(b.taux_libelle", real)
        self.assertIn('(v == null) ? "non disponible"', real)  # jamais 0 sans taux
        self.assertEqual(plans.count("${escHtml(prog.taux_libelle"), 2)  # carte et détail d'un plan
        self.assertIn("prog.pnl_total_eur", plans)

    def test_saisie_dans_la_devise_de_cotation(self):
        real = lire("real.html")
        self.assertEqual(real.count('placeholder="Montant (devise de cotation, $ pour les actions US)"'), 2)
        self.assertIn("(${sym(devise)}, devise de cotation)", real)  # invite de calibration
        self.assertIn("Prix de sortie (${s}, devise de la position)", real)


if __name__ == "__main__":
    unittest.main()
