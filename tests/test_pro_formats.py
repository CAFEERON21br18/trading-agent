"""
tests/test_pro_formats.py — Mise en forme des chiffres et courbe SVG du dashboard professionnel
(dashboard/pro/formats.py, courbe_svg.py, chiffres.py).

1. un gain porte « + », une perte « − », zéro n'a pas de signe ; valeur absente : « — » ;
2. écriture française : virgule, espace insécable, symbole ou code de devise ;
3. la couleur ne fait que répéter le signe ;
4. badge « non décidable · n / 100 » sous 100 trades, absent à partir de 100 ;
5. courbe : SVG sans script ni adresse externe, un point par jour, valeurs signées dans le
   titre ; série vide : rien.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_formats -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.pro import chiffres, courbe_svg, formats

E = formats.ESPACE


class TestFormats(unittest.TestCase):
    def test_signe_toujours_ecrit(self):
        for valeur, attendu in [(D("12.3"), f"+12,30{E}€"), (D("-5"), f"−5,00{E}€"), (D("0"), f"0,00{E}€"),
                                (D("-0.001"), f"0,00{E}€"), (62.0, f"+62,00{E}€"), (D("1234.565"), f"+1{E}234,57{E}€"),
                                (None, "—")]:
            with self.subTest(valeur=valeur):
                self.assertEqual(formats.montant_signe(valeur, "EUR"), attendu)
        self.assertEqual(formats.montant_signe(D("-77.5"), "USD"), f"−77,50{E}$")
        self.assertEqual(formats.montant_signe(D("3"), "GBP"), f"+3,00{E}GBP")

    def test_montant_sans_signe_pourcent_r_quantite_jour(self):
        self.assertEqual(formats.montant(D("3.6"), "EUR"), f"3,60{E}€")
        self.assertEqual(formats.montant(D("-0.12"), "USD"), f"−0,12{E}$")
        self.assertEqual(formats.montant(None, "EUR"), "—")
        self.assertEqual([formats.pourcent(v) for v in (0.5, 0.03125, 1, None)],
                         [f"50,0{E}%", f"3,1{E}%", f"100,0{E}%", "—"])
        self.assertEqual([formats.en_r(v) for v in (2.0, D("-0.5"), 0, None)],
                         [f"+2,00{E}R", f"−0,50{E}R", f"0,00{E}R", "—"])
        self.assertEqual([formats.quantite(v) for v in (D("2.500000"), D("10"), D("0.000123"), D("1500"), None)],
                         ["2,5", "10", "0,000123", f"1{E}500", "—"])
        self.assertEqual(formats.jour(datetime(2026, 11, 5, 23, tzinfo=timezone.utc)), "05/11/2026")
        self.assertEqual((formats.jour(date(2026, 1, 9)), formats.jour(None)), ("09/01/2026", "—"))

    def test_la_couleur_repete_le_signe(self):
        self.assertEqual([formats.classe(v) for v in (D("1"), D("-1"), D("0"), D("-0.001"), None)],
                         ["text-emerald-400", "text-red-400", "", "", ""])

    def test_badge_sous_le_seuil(self):
        self.assertEqual((chiffres.badge(0), chiffres.badge(99), chiffres.badge(100), chiffres.badge(250)),
                         ("non décidable · 0 / 100", "non décidable · 99 / 100", "", ""))
        self.assertEqual((chiffres.pluriel(1, "trade"), chiffres.pluriel(2, "trade"), chiffres.pluriel(0, "ordre")),
                         ("1 trade", "2 trades", "0 ordre"))


class TestCourbe(unittest.TestCase):
    SERIE = [(date(2026, 11, 5), D("78.4")), (date(2026, 11, 6), D("62.0")), (date(2026, 11, 9), D("-10"))]

    def test_svg_sans_script_ni_adresse_externe(self):
        svg = courbe_svg.courbe(self.SERIE, "EUR", "Cumul <compte>")
        self.assertTrue(svg.startswith("<svg ") and svg.endswith("</svg>"))
        self.assertEqual((svg.count("<circle"), svg.count("<polyline")), (3, 1))
        for interdit in ("<script", "href", "javascript", "<compte>"):
            self.assertNotIn(interdit, svg)
        self.assertEqual(svg.count("http"), 1)  # le seul : l'espace de noms SVG, qui n'est pas un appel
        self.assertIn("Cumul &lt;compte&gt;", svg)
        titre = svg[svg.index("<title>"):svg.index("</title>")]
        for attendu in (f"−10,00{E}€ au 09/11/2026", f"plus haut +78,40{E}€", f"plus bas −10,00{E}€", "3 jour(s)"):
            self.assertIn(attendu, titre)
        self.assertIn('role="img"', svg)

    def test_serie_vide_ou_d_un_seul_point(self):
        self.assertEqual(courbe_svg.courbe([], "EUR", "x"), "")
        un = courbe_svg.courbe(self.SERIE[:1], "USD", "x")
        self.assertEqual(un.count("<circle"), 1)
        self.assertIn(f"+78,40{E}$", un)


if __name__ == "__main__":
    unittest.main()
