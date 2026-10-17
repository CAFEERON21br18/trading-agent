"""
tests/test_report_sections.py — TODO §17 : sections News et Fondamentaux du rapport quotidien, pour les
seuls BUY et SELL du cycle, en affichage seulement.
- News : NewsAPI seulement, 1 requête par actif, 10 au plus par jour (compteur partagé entre routines
  du même jour) ; clé absente, plafond, erreur ou réponse vide → « non disponible » ; pas de Yahoo RSS ;
- Fondamentaux : analyse déjà faite par le cycle, aucun appel Alpha Vantage.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_report_sections -v
NewsAPI simulé (aucun appel réel), compteur dans un dossier temporaire, valeurs inventées.
"""

import json
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

import config
from agents import report_sections as rs
from agents.analysts.sentiment_analyst import news_fetcher

NEWS = [{"titre": "Titre inventé en hausse", "source": "Source inventée", "impact": "positif"},
        {"titre": "Autre titre inventé", "source": "Autre source", "impact": "neutre"}]


def d(ticker, action="BUY", fondamental=None):
    return {"ticker": ticker, "decision": {"ticker": ticker, "decision": action, "confidence": 7},
            "analyses": {"fondamental": fondamental} if fondamental is not None else {}}


class BaseNews(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(rs, "COMPTEUR", os.path.join(self.dossier.name, "rapport_newsapi.json")),
                       mock.patch.object(config, "NEWSAPI_KEY", "cle-inventee"),
                       mock.patch.object(news_fetcher, "recuperer_news_yahoo_rss", side_effect=AssertionError("pas de RSS")),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def news(self, decisions, effet=None):
        with mock.patch.object(news_fetcher, "recuperer_news_newsapi",
                               side_effect=effet or (lambda t, n: NEWS)) as appel:
            return rs.section_news(decisions), appel


class TestNews(BaseNews):
    def test_une_requete_par_actif_buy_ou_sell(self):
        texte, appel = self.news([d("AAA"), d("BBB", "SELL"), d("CCC", "HOLD")])
        self.assertEqual([c.args for c in appel.call_args_list], [("AAA", 3), ("BBB", 3)])
        self.assertIn("### AAA — BUY (7/10)\n- 🟢 Titre inventé en hausse — _Source inventée_", texte)
        self.assertIn("### BBB — SELL (7/10)", texte)
        self.assertNotIn("CCC", texte)

    def test_plafond_de_10_par_jour_entre_routines(self):
        texte, appel = self.news([d(f"T{i:02d}") for i in range(12)])
        self.assertEqual(appel.call_count, 10)
        self.assertEqual(texte.count("non disponible (plafond de 10 requêtes du jour)"), 2)
        texte, appel = self.news([d("AAA")])  # seconde routine du même jour (manuelle)
        self.assertEqual(appel.call_count, 0)
        self.assertIn("plafond", texte)
        with open(rs.COMPTEUR, "w", encoding="utf-8") as f:
            json.dump({"jour": "2026-01-01", "requetes": 10}, f)  # autre jour : remis à zéro
        self.assertEqual(self.news([d("AAA")])[1].call_count, 1)

    def test_cle_absente_erreur_ou_vide(self):
        with mock.patch.object(config, "NEWSAPI_KEY", ""):
            texte, appel = self.news([d("AAA")])
        self.assertEqual((appel.call_count, texte.count("non disponible (clé NewsAPI absente)")), (0, 1))
        for effet in (RuntimeError("429 simulé"), lambda t, n: []):
            with self.subTest(effet=effet):
                texte, _ = self.news([d("AAA")], effet)
                self.assertIn("### AAA — BUY (7/10)\n- non disponible", texte)

    def test_aucun_buy_ni_sell(self):
        texte, appel = self.news([d("AAA", "HOLD")])
        self.assertEqual((texte, appel.call_count), ("", 0))


class TestFondamentaux(unittest.TestCase):
    def test_analyse_du_cycle_sans_alpha_vantage(self):
        with mock.patch("agents.analysts.fundamental_analyst.alphavantage._appel_av",
                        side_effect=AssertionError("aucun appel Alpha Vantage")):
            texte = rs.section_fondamentaux([
                d("AAA", fondamental={"evaluation": "Valorisation inventée", "direction": "POSITIF", "confiance": 6}),
                d("BBB", "SELL", fondamental={"evaluation": "Données indisponibles", "confiance": 0}),
                d("CCC", "SELL"), d("DDD", "HOLD", fondamental={"evaluation": "X", "confiance": 9})])
        self.assertIn("### AAA — BUY (7/10)\n- Évaluation : Valorisation inventée | direction POSITIF | confiance 6/10", texte)
        self.assertIn("### BBB — SELL (7/10)\n- non disponible", texte)
        self.assertIn("### CCC — SELL (7/10)\n- non disponible", texte)
        self.assertNotIn("DDD", texte)
        self.assertEqual(rs.section_fondamentaux([d("DDD", "HOLD")]), "")


if __name__ == "__main__":
    unittest.main()
