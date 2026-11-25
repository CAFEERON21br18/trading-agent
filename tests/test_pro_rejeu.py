"""
tests/test_pro_rejeu.py — Page « Rejeu » du dashboard professionnel (GET /pro/rejeu).

1. le verdict et ses trois conditions, toujours ceux de la configuration du critère ;
2. le choix de la configuration (six liens) ; une autre configuration est dite « mesure de
   sensibilité » ; une valeur inconnue revient à la configuration qui décide ;
3. le tableau par année ; la stratégie et les deux références sur le même graphique, distinguées
   par leur trait et nommées, sans texte dans le dessin ;
4. les mentions « hypothèses de frais CFD » et « biais de sélection » restent visibles, même
   quand le rejeu n'a jamais été lancé ;
5. lecture seule : GET seulement, grand livre du rejeu inchangé, data/ledger.db jamais ouvert ;
   le calcul est gardé en mémoire tant que le fichier ne change pas.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_rejeu -v
Grand livre du rejeu fabriqué dans un dossier temporaire ; aucun réseau, rien dans data/.
"""

import os
import re
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.app import app
from dashboard.pro import courbe_rejeu, rejeu_vue
from rejeu import etude, grand_livre, lancement
from rejeu import parametres as P
from tests.pro_fixtures import empreinte
from tests.pro_page_fixtures import EN_TETE, texte_de
from tests.rejeu_fixtures import analyses_de, bougies, jours_ouvres

J = jours_ouvres(date(2018, 1, 1), 4)
PLAT = (100, 100.5, 99.5, 100)


class TestPageRejeu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.dossier = os.path.join(cls.tmp.name, "rejeu")
        barres = {"AAPL": bougies(J, [PLAT, (100, 101, 99, 100.5), (100.5, 107, 100, 106.5), (106.5, 107, 106, 106.5)]),
                  "MSFT": bougies(J, [PLAT] * 4)}
        analyses = {"AAPL": analyses_de(barres["AAPL"], {J[0]: ("ACHAT", 9)}), "MSFT": analyses_de(barres["MSFT"], {})}
        lancement.lancer(cls.dossier, os.path.join(cls.tmp.name, "rapports"), processus=1, barres=barres, analyses=analyses)

    def setUp(self):
        correctif = mock.patch.object(P, "DOSSIER", self.dossier)
        correctif.start()
        self.addCleanup(correctif.stop)
        rejeu_vue._memoire.clear()
        self.client = app.test_client()

    def page(self, url="/pro/rejeu") -> str:
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200, url)
        return reponse.get_data(as_text=True)

    def section(self, html: str, identifiant: str) -> str:
        debut = html.index(">", html.index(f'id="{identifiant}"')) + 1
        return texte_de(html[debut:html.index("</section>", debut)])

    def test_verdict_et_ses_trois_conditions(self):
        html = self.page()
        verdict = self.section(html, "verdict")
        self.assertIn("Verdict : « non décidable »", verdict)
        self.assertIn("Configuration qui décide : 1 000 € · Revolut, années 2018–2025, 1 trades clos", verdict)
        self.assertEqual(re.findall(r"Condition (\d) : (vraie|fausse)", verdict), [("1", "fausse"), ("2", "fausse"), ("3", "fausse")])
        self.assertIn("espérance nette +1,00 € par trade sur 1 trades", verdict)
        self.assertIn("moins de 100 trades clos : « non décidable »", verdict)

    def test_mentions_toujours_visibles(self):
        for html in (self.page(), self.page("/pro/rejeu?capital=10000&profil=cfd")):
            mentions = self.section(html, "mentions")
            self.assertIn("Hypothèses de frais CFD : écart de 0,10 % par côté", mentions)
            self.assertIn("Biais de sélection : l'univers est la liste de 2026", mentions)
        with tempfile.TemporaryDirectory() as vide, mock.patch.object(P, "DOSSIER", vide):
            html = self.page()
            self.assertIn("Le rejeu n'a pas encore été lancé sur cette machine", texte_de(html))
            self.assertIn("Hypothèses de frais CFD", self.section(html, "mentions"))
            self.assertIn("Biais de sélection", self.section(html, "mentions"))
            self.assertNotIn('id="verdict"', html)
            self.assertEqual(os.listdir(vide), [])  # la page ne crée rien

    def test_choix_de_la_configuration(self):
        html = self.page()
        liens = re.findall(r'href="/pro/rejeu\?capital=(\d+)&amp;profil=(\w+)"( aria-current="true")?', html)
        self.assertEqual(len(liens), 6)
        self.assertEqual([(c, p) for c, p, courant in liens if courant], [("1000", "revolut")])
        self.assertNotIn("Mesure de sensibilité", html)
        autre = self.page("/pro/rejeu?capital=10000&profil=cfd")
        config = self.section(autre, "configuration")
        self.assertIn("Configuration affichée : 10 000 € · CFD", config)
        self.assertIn("Mesure de sensibilité : cette configuration ne fonde pas le verdict", config)
        self.assertIn("Configuration qui décide : 1 000 € · Revolut", self.section(autre, "verdict"))  # le verdict ne change pas
        self.assertIn("Résultat net +1,00 €", self.section(html, "configuration"))
        self.assertIn("Frais payés 2,00 €", self.section(html, "configuration"))
        for inconnue in ("/pro/rejeu?capital=5&profil=revolut", "/pro/rejeu?capital=abc&profil=<b>"):
            self.assertIn("Configuration affichée : 1 000 € · Revolut", self.section(self.page(inconnue), "configuration"))

    def test_tableau_par_annee_et_courbes_sur_le_meme_graphique(self):
        html = self.page()
        tableau = html[html.index('id="annees"'):]
        lignes = [texte_de(l) for l in re.findall(r"<tr class=.*?</tr>", tableau, re.S)]
        self.assertEqual([l.split(" ")[0] for l in lignes], [str(a) for a in range(2018, 2026)] + ["2018–2025"])
        self.assertTrue(lignes[0].startswith("2018 1 +1,00 € +1,00 € — 100,0 %"))
        self.assertTrue(lignes[1].startswith("2019 0 — — —"))  # non calculable : jamais zéro
        courbe = html[html.index('id="courbe"'):html.index('id="annees"')]
        dessin = courbe[courbe.index('<svg viewBox="0 0 100 100"'):courbe.rindex("</svg>")]
        self.assertEqual((courbe.count("<figure"), dessin.count("<polyline")), (1, 3))  # un seul graphique, trois courbes
        self.assertNotIn("<text", courbe)
        legende = texte_de(courbe[courbe.index("<figcaption"):courbe.index("</figcaption>")])
        for attendu in ("Stratégie (trait plein) : 1 001,00 €", "Référence rachetée chaque année (trait tirets)",
                        "Référence gardée sur la période (trait pointillé)"):
            self.assertIn(attendu, legende)

    def test_lecture_seule_et_calcul_garde_en_memoire(self):
        chemin = grand_livre.chemin(self.dossier)
        avant = empreinte(chemin)
        production = os.path.join(RACINE, "data", "ledger.db")
        etat = os.path.exists(production) and os.path.getmtime(production)
        with mock.patch.object(etude, "lire", wraps=etude.lire) as lire:
            self.page()
            self.page()
            self.page("/pro/rejeu?capital=100&profil=revolut")
            self.assertEqual(lire.call_count, 2)  # 1 000 € Revolut une fois, 100 € Revolut une fois
        self.assertEqual(empreinte(chemin), avant)
        self.assertEqual(os.path.exists(production) and os.path.getmtime(production), etat)
        self.assertEqual(self.client.post("/pro/rejeu", headers=EN_TETE).status_code, 405)
        with open(os.path.join(RACINE, "dashboard", "templates", "pro_rejeu.html"), encoding="utf-8") as f:
            gabarit = f.read()
        for interdit in ("://", "<script", "|safe", "<form", "fetch("):
            self.assertNotIn(interdit, gabarit)
        with open(os.path.join(RACINE, "dashboard", "templates", "pro_vue.html"), encoding="utf-8") as f:
            self.assertIn('href="/pro/rejeu"', f.read())

    def test_lecture_en_echec(self):
        with mock.patch.object(rejeu_vue, "_etude", side_effect=RuntimeError("secret")):
            html = self.page()
        self.assertIn("Le grand livre du rejeu n'a pas pu être lu", texte_de(html))
        self.assertNotIn("secret", html)
        self.assertIn("Biais de sélection", self.section(html, "mentions"))


class TestCourbeRejeu(unittest.TestCase):
    def test_traits_nommes_et_valeur_negative(self):
        jours = [date(2018, 1, n) for n in range(1, 13)]
        series = [("Stratégie <b>", [(j, D(1000 - 100 * i)) for i, j in enumerate(jours)]),  # finit à −100
                  ("Référence", [(j, D(1000 + 50 * i)) for i, j in enumerate(jours)])]
        html = courbe_rejeu.courbe(series, "EUR", "Valeur")
        self.assertEqual((html.count("<polyline"), html.count("stroke-dasharray")), (2, 2))  # 2 courbes ; tirets : légende et tracé
        self.assertIn("Stratégie &lt;b&gt; (trait plein)", html)
        self.assertNotIn("<b>", html)
        axe = html[html.index('data-axe="y"'):html.index("<svg viewBox=\"0 0 100 100\"")]
        self.assertIn(">0<", axe)
        self.assertIn("−500 €", axe)  # l'axe descend sous zéro
        self.assertEqual(courbe_rejeu.courbe([("x", [(jours[0], D(1))])], "EUR", "x"), "")


if __name__ == "__main__":
    unittest.main()
