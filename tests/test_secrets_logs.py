"""
tests/test_secrets_logs.py — Aucune clé d'API ni jeton dans les logs (clé NewsAPI relevée en clair dans
logs/tactical_errors.log, URL des erreurs 429).

1. utils.secret_mask : chaque forme de clé (NewsAPI, Alpha Vantage, CoinGecko, Groq, Gemini, TypeSafe,
   email, jeton générique ; URL, en-tête, paramètres affichés, valeur d'une variable du .env) ressort masquée ;
2. FiltreSecrets posé par utils.logger sur chaque handler (et sur le handler de dernier recours) :
   message, arguments et trace d'exception écrits masqués dans le fichier ;
3. masquage explicite aux endroits connus : erreurs HTTP de requests (NewsAPI, Alpha Vantage,
   CoinGecko), exception du SDK Groq, échec SMTP.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_secrets_logs -v
Clés inventées ; requests, Groq et SMTP simulés : aucun appel réseau.
"""

import logging
import os
import sys
import unittest
import uuid
from unittest import mock

import requests

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import config
from utils.logger import get_logger
from utils.secret_mask import FiltreSecrets, masquer_secrets

NEWS, AV, CG = "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "QWERTYUIOP123456", "CG-abcdefghij123456"
GROQ, GOOGLE, TS = "gsk_" + "Ab1" * 10, "AIza" + "Zy9_" * 9, "ts-live-9f8e7d6c5b4a3210"
FORMES = {
    "NewsAPI (URL)": f"429 Client Error for url: https://newsapi.org/v2/everything?q=AAA&apiKey={NEWS}&language=en",
    "Alpha Vantage (URL)": f"for url: https://www.alphavantage.co/query?function=OVERVIEW&symbol=X&apikey={AV}",
    "CoinGecko (URL)": f"for url: https://api.coingecko.com/api/v3/global?x_cg_demo_api_key={CG}",
    "CoinGecko (en-tête)": f"headers={{'x-cg-demo-api-key': '{CG}'}}",
    "Groq (clé)": f"Error code: 401 - invalid key {GROQ}",
    "Groq (en-tête)": f"Authorization: Bearer {GROQ}",
    "Gemini (URL)": f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE}",
    "Gemini (en-tête)": f"x-goog-api-key: {GOOGLE}",
    "TypeSafe (paramètre)": f"TypeSafeClient(api_key='{TS}', model='m')",
    "jeton (JSON)": f'{{"token": "{TS}"}}',
    "jeton (URL)": f"https://exemple.test/a?access_token={TS}&x=1",
}
SECRETS = (NEWS, AV, CG, GROQ, GOOGLE, TS)


def erreur_http(url: str) -> requests.HTTPError:
    reponse = requests.Response()
    reponse.status_code, reponse.reason, reponse.url = 429, "Too Many Requests", url
    try:
        reponse.raise_for_status()
    except requests.HTTPError as e:
        return e


class TestMasque(unittest.TestCase):
    def test_chaque_forme(self):
        for forme, texte in FORMES.items():
            with self.subTest(forme=forme):
                masque = masquer_secrets(texte)
                self.assertFalse([s for s in SECRETS if s in masque], masque)
                self.assertIn("***", masque)

    def test_valeur_d_une_variable_du_env(self):
        with mock.patch.dict(os.environ, {"EMAIL_APP_PASSWORD": "abcd efgh ijkl mnop", "TYPESAFE_API_KEY": TS}):
            masque = masquer_secrets("SMTP 535 abcd efgh ijkl mnop refusé ; clé " + TS)
        self.assertNotIn("abcd efgh ijkl mnop", masque)
        self.assertIn("***EMAIL_APP_PASSWORD***", masque)
        self.assertIn("***TYPESAFE_API_KEY***", masque)

    def test_texte_ordinaire_intact(self):
        for texte in ("max_tokens=4000", "Groq KO (rate_limit_groq)", "Score +2.10, confiance 7/10"):
            self.assertEqual(masquer_secrets(texte), texte)


class TestFiltre(unittest.TestCase):
    def test_handlers_du_logger(self):
        repere = uuid.uuid4().hex
        with mock.patch.object(sys, "stderr"):  # handler console créé ici : rien à l'écran pendant les tests
            logger = get_logger(f"test_secrets_{repere}")
            self.assertTrue(all(any(isinstance(f, FiltreSecrets) for f in h.filters) for h in logger.handlers))
            self.assertTrue(any(isinstance(f, FiltreSecrets) for f in logging.lastResort.filters))
            logger.error(f"{repere} message : {FORMES['NewsAPI (URL)']}")
            logger.error("%s arguments : %s", repere, FORMES["Groq (en-tête)"])
            try:
                raise ValueError(FORMES["Gemini (URL)"])
            except ValueError:
                logger.exception(f"{repere} trace")
        fichier = next(h.baseFilename for h in logger.handlers if hasattr(h, "baseFilename"))
        for h in logger.handlers:
            h.flush()
        with open(fichier, encoding="utf-8") as f:
            ecrit = f.read()
        self.assertGreaterEqual(ecrit.count(repere), 3)  # tests : journal et erreurs dans le même fichier
        self.assertFalse([s for s in SECRETS if s in ecrit])
        self.assertIn("apiKey=***", ecrit)

    def test_filtre_ne_bloque_jamais(self):
        enregistrement = logging.LogRecord("x", logging.ERROR, __file__, 1, "%s %s", ("un seul",), None)
        self.assertTrue(FiltreSecrets().filter(enregistrement))  # arguments faux : la ligne passe quand même


class TestEndroitsConnus(unittest.TestCase):
    def verifier(self, logger, appel):
        with self.assertLogs(logger, "ERROR") as journal:  # handler du test, sans filtre : masquage explicite
            appel()
        texte = "\n".join(journal.output)
        self.assertFalse([s for s in SECRETS if s in texte], texte)
        self.assertIn("***", texte)

    def test_newsapi_alphavantage_coingecko(self):
        from agents.analysts.sentiment_analyst import news_fetcher
        from agents.analysts.fundamental_analyst import alphavantage, onchain
        with mock.patch.object(config, "NEWSAPI_KEY", NEWS), mock.patch.object(config, "ALPHA_VANTAGE_KEY", AV):
            with mock.patch.object(news_fetcher.requests, "get", side_effect=erreur_http(FORMES["NewsAPI (URL)"][25:])):
                self.verifier(news_fetcher.logger, lambda: news_fetcher.recuperer_news_newsapi("AAA"))
            with mock.patch.object(alphavantage.requests, "get", side_effect=erreur_http(FORMES["Alpha Vantage (URL)"][9:])):
                self.verifier(alphavantage.logger, lambda: alphavantage._appel_av("OVERVIEW", "X"))
        from utils import cache
        import tempfile
        # cache CoinGecko (v1.9) isolé : une dominance fraîche sur disque masquerait l'erreur simulée
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cache, "CACHE_DIR", tmp), \
                mock.patch.object(onchain, "_dormir"), \
                mock.patch.object(onchain.requests, "get", side_effect=erreur_http(FORMES["CoinGecko (URL)"][9:])):
            self.verifier(onchain.logger, onchain.recuperer_dominance_btc)

    def test_groq(self):
        from utils import llm
        client = mock.MagicMock()
        client.chat.completions.create.side_effect = RuntimeError(f"connexion refusée pour {GROQ}")
        with mock.patch.object(llm, "cle_groq", return_value=GROQ), mock.patch("groq.Groq", return_value=client):
            r = llm._try_groq("q", None, 0.2, 10)
        self.assertNotIn(GROQ, r["error"])

    def test_email(self):
        import smtplib
        from alerts.channels import email_channel as ec
        mot_de_passe = "wxyz abcd efgh ijkl"  # mot de passe d'application inventé, lu dans l'environnement
        refus = smtplib.SMTPAuthenticationError(535, f"refusé pour {mot_de_passe}".encode())
        with mock.patch.dict(os.environ, {"EMAIL_APP_PASSWORD": mot_de_passe}), \
                mock.patch.object(ec, "_envoi_smtp", side_effect=refus), \
                mock.patch.object(ec, "_sauvegarder_localement", return_value=""):
            with self.assertLogs(ec.logger, "ERROR") as journal:
                ec.envoyer_email("sujet", "corps")
        self.assertNotIn(mot_de_passe, "\n".join(journal.output))
        self.assertIn("***EMAIL_APP_PASSWORD***", "\n".join(journal.output))


if __name__ == "__main__":
    unittest.main()
