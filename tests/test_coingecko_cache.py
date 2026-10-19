"""
tests/test_coingecko_cache.py — Cache CoinGecko du fondamental crypto (REGISTRE_CRITERES v1.9, §9.8 b).

1. Un passage sur les 5 cryptos de la watchlist (dominance de l'orchestrateur, puis analyse
   fondamentale de chaque crypto) fait au plus 1 appel de dominance, et 1 appel par pièce couverte ;
2. un 429 simulé ne vide pas le fondamental quand le cache est valide (aucun appel) ; cache périmé
   et 429 : comportement d'avant (fondamental indisponible) ;
3. format renvoyé identique (réseau ou cache) et score fondamental inchangé ;
4. appels espacés d'au moins ESPACEMENT_S dans un même processus.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_coingecko_cache -v
CoinGecko simulé (requests.get remplacé) et réseau piégé ; cache en dossier temporaire.
"""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

import requests

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import cache
from agents.analysts.fundamental_analyst import analyst, onchain

CRYPTOS = ["BTC-USD", "ETH-USD", "SOL-USD", "HBAR-USD", "CRO-USD"]


class Reponse:
    def __init__(self, donnees=None, statut=200):
        self.donnees, self.statut = donnees, statut

    def raise_for_status(self):
        if self.statut >= 400:
            raise requests.HTTPError(f"{self.statut} Client Error: Too Many Requests")

    def json(self):
        return self.donnees


def coin(nom):  # données de marché inventées
    return {"name": nom, "market_data": {
        "current_price": {"usd": 90.0}, "ath": {"usd": 120.0}, "market_cap": {"usd": 4.0e10},
        "total_volume": {"usd": 2.0e9}, "price_change_percentage_24h": 1.5, "price_change_percentage_7d": -3.0,
        "price_change_percentage_30d": 8.0, "market_cap_rank": 7}}


class BaseCoinGecko(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.appels, self.statut = [], 200
        self.patchs = [mock.patch.object(cache, "CACHE_DIR", self.dossier.name),
                       mock.patch.object(onchain, "_dormir"),
                       mock.patch.object(onchain.requests, "get", side_effect=self.faux_get),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))]
        for p in self.patchs:
            p.start()
        onchain._dernier_appel[0] = 0.0

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        onchain._dernier_appel[0] = 0.0
        self.dossier.cleanup()

    def faux_get(self, url, **kwargs):
        self.appels.append(url.rsplit("/", 1)[-1])
        if self.statut != 200:
            return Reponse(statut=self.statut)
        if url.endswith("/global"):
            return Reponse({"data": {"market_cap_percentage": {"btc": 56.2}}})
        return Reponse(coin(url.rsplit("/", 1)[-1]))

    def passage(self) -> dict:
        """Dominance de l'orchestrateur, puis analyse fondamentale des 5 cryptos (comme un cycle)."""
        onchain.recuperer_dominance_btc()
        return {t: analyst.analyser_actif(t) for t in CRYPTOS}

    @staticmethod
    def sans_horodatage(rapport):
        return [l for l in rapport.splitlines() if not l.startswith("ANALYSE FONDAMENTALE")]

    def perimer(self):
        """Vieillit tous les fichiers du cache de 11 minutes."""
        for racine, _, fichiers in os.walk(self.dossier.name):
            for f in fichiers:
                t = time.time() - 11 * 60
                os.utime(os.path.join(racine, f), (t, t))


class TestPassage(BaseCoinGecko):
    def test_une_seule_dominance_par_passage(self):
        rapports = self.passage()
        self.assertEqual(self.appels.count("global"), 1)
        self.assertEqual(sorted(a for a in self.appels if a != "global"), ["bitcoin", "ethereum", "solana"])
        for t in ("BTC-USD", "ETH-USD", "SOL-USD"):
            self.assertIn("Dominance BTC     : 56.2%", rapports[t])
        self.assertTrue(rapports["HBAR-USD"].startswith("❌ Type d'actif inconnu"))  # inchangé

    def test_marqueur_de_date_effective_au_registre(self):
        from utils import registre
        self.assertEqual(registre.parametres_actifs()["QUALITE_DONNEES"], 1)  # §9.8 : date effective

    def test_appels_espaces(self):
        onchain.recuperer_dominance_btc()
        onchain.recuperer_donnees_coin("BTC-USD")
        (attente,), _ = onchain._dormir.call_args
        self.assertTrue(0 < attente <= onchain.ESPACEMENT_S)


class Test429(BaseCoinGecko):
    def test_429_cache_valide_fondamental_garde(self):
        avant = self.passage()
        n = len(self.appels)
        self.statut = 429
        apres = self.passage()
        self.assertEqual(len(self.appels), n)  # cache valide : aucun appel, donc aucun 429
        for t in CRYPTOS:
            self.assertEqual(self.sans_horodatage(apres[t]), self.sans_horodatage(avant[t]))  # même score

    def test_429_cache_perime_comme_avant(self):
        self.passage()
        self.perimer()
        self.statut = 429
        self.assertTrue(analyst.analyser_actif("SOL-USD").startswith("❌ Données CoinGecko indisponibles"))
        self.assertIsNone(onchain.recuperer_dominance_btc())

    def test_format_identique_reseau_et_cache(self):
        reseau = onchain.recuperer_donnees_coin("SOL-USD")
        self.assertEqual(onchain.recuperer_donnees_coin("SOL-USD"), reseau)
        self.assertEqual(self.appels.count("solana"), 1)
        self.assertEqual(set(reseau), {"nom", "market_cap", "volume_24h", "variation_24h", "variation_7j",
                                       "variation_30j", "ath", "distance_ath_pct", "rang_market_cap"})
        self.assertEqual(onchain.recuperer_dominance_btc(), onchain.recuperer_dominance_btc())


if __name__ == "__main__":
    unittest.main()
