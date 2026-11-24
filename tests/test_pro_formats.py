"""
tests/test_pro_formats.py — Mise en forme des chiffres et courbe SVG du dashboard professionnel
(dashboard/pro/formats.py, courbe_svg.py, chiffres.py).

1. un gain porte « + », une perte « − », zéro n'a pas de signe ; valeur absente : « — » ;
2. écriture française : virgule, espace insécable, symbole ou code de devise ;
3. la couleur ne fait que répéter le signe ;
4. badge « non décidable · n / 100 » sous 100 trades, absent à partir de 100 ;
5. courbe : aucun texte dans le dessin ; « plus haut » et « plus bas » dans leur zone, jamais
   dans celle des graduations ; graduations rondes, espacées, avec le zéro ; sans script ni
   adresse externe ; moins de deux jours de clôture : pas de graphique, une phrase.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_formats -v
Calcul pur sur des valeurs inventées : aucune base, aucun réseau, aucun .env.
"""

import os
import re
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.pro import chiffres, courbe_svg, donnees, formats, vue_ensemble

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

    def zone(self, html: str, marqueur: str, balise: str) -> str:
        """Contenu de la zone qui porte ce marqueur."""
        debut = html.index(marqueur)
        return html[html.index(">", debut) + 1:html.index(f"</{balise}>", debut)]

    def test_aucun_texte_dans_le_dessin_et_zones_separees(self):
        html = courbe_svg.courbe(self.SERIE, "EUR", "Cumul <compte>")
        self.assertTrue(html.startswith("<figure ") and html.endswith("</figure>"))
        dessin = html[html.index("<svg"):html.index("</svg>")]
        for interdit in ("<text", "<title", "plus haut", "plus bas", "€"):
            self.assertNotIn(interdit, dessin)  # le dessin s'étire : aucun texte dedans
        self.assertEqual((dessin.count("<polyline"), dessin.count('stroke-width="6"')), (1, 3))  # 3 points
        self.assertIn('preserveAspectRatio="none"', dessin)
        for interdit in ("<script", "href", "javascript", "<compte>", "http", "<circle"):
            self.assertNotIn(interdit, html)
        legende = self.zone(html, "<figcaption", "figcaption")
        self.assertEqual(re.sub(r"<[^>]+>", "", legende),
                         f"plus haut +78,40{E}€plus bas −10,00{E}€dernier −10,00{E}€")
        axe_y = self.zone(html, 'data-axe="y"', "div")
        axe_x = self.zone(html, 'data-axe="x"', "div")
        for libelle in ("plus haut", "plus bas"):
            self.assertNotIn(libelle, axe_y + axe_x)  # jamais dans la zone des graduations
        self.assertEqual(re.findall(r">([^<]+)</span>", axe_x), ["05/11/2026", "09/11/2026"])
        self.assertLess(html.index("</figcaption>"), html.index('data-axe="y"'))  # la légende est au-dessus
        self.assertIn("Cumul &lt;compte&gt; : −10,00", html)
        self.assertIn("3 jours de clôture", html)
        self.assertIn('role="img"', html)

    def test_graduations_rondes_espacees_avec_le_zero(self):
        html = courbe_svg.courbe(self.SERIE, "EUR", "x")
        axe_y = self.zone(html, 'data-axe="y"', "div")
        libelles = re.findall(r'top:([0-9.]+)%[^>]*>([^<]+)</span>', axe_y)
        self.assertEqual([texte for _, texte in libelles],
                         [f"+100{E}€", f"+50{E}€", "0", f"{formats.MOINS}50{E}€"])
        hauteurs = [float(h) for h, _ in libelles]
        self.assertEqual((hauteurs[0], hauteurs[-1]), (0.0, 100.0))
        self.assertTrue(all(b - a >= 15 for a, b in zip(hauteurs, hauteurs[1:])), hauteurs)  # jamais collées
        for bas, haut, attendu in [("-8", "19.2", ["20", "10", "0", "-10"]), ("0", "78.4", ["80", "60", "40", "20", "0"]),
                                   ("62", "78.4", ["80", "60", "40", "20", "0"]), ("0", "0.3", ["0.3", "0.2", "0.1", "0.0"]),
                                   ("-1234", "-200", ["0", "-500", "-1000", "-1500"]), ("0", "0", ["1", "0"])]:
            with self.subTest(bas=bas, haut=haut):
                axe = courbe_svg.graduations(D(bas), D(haut))
                self.assertEqual(axe, [D(a) for a in attendu])
                self.assertLessEqual(len(axe), 7)
        petit = courbe_svg.courbe([(date(2026, 11, 5), D("0.12")), (date(2026, 11, 6), D("0.3"))], "USD", "x")
        self.assertIn(f"+0,10{E}$", self.zone(petit, 'data-axe="y"', "div"))  # centimes : deux décimales

    def test_moins_de_deux_jours_pas_de_graphique(self):
        self.assertEqual(courbe_svg.courbe([], "EUR", "x"), "")
        self.assertEqual(courbe_svg.courbe(self.SERIE[:1], "USD", "x"), "")
        self.assertTrue(courbe_svg.courbe(self.SERIE[:2], "USD", "x").startswith("<figure"))

    def test_phrase_a_la_place_du_graphique(self):
        un_jour = donnees.Bloc([(date(2026, 11, 5), D("-12.5"))])
        self.assertEqual(vue_ensemble.phrase_sans_courbe(un_jour, 3, "EUR"),
                         f"3 trades clos sur un seul jour de clôture, résultat net réalisé −12,50{E}€. "
                         "Pas de graphique avant un deuxième jour de clôture.")
        self.assertEqual(vue_ensemble.phrase_sans_courbe(donnees.Bloc([]), 0, "EUR"), "Aucun trade clos sur la période.")
        self.assertEqual(vue_ensemble.phrase_sans_courbe(donnees.Bloc(indisponible="taux indisponible"), 1, "EUR"),
                         "1 trade clos ; résultat net réalisé : taux indisponible.")
        self.assertEqual(vue_ensemble.phrase_sans_courbe(donnees.Bloc(self.SERIE), 4, "EUR"), "")  # il y a un graphique


if __name__ == "__main__":
    unittest.main()
