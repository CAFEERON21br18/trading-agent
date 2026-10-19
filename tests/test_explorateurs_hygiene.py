"""
tests/test_explorateurs_hygiene.py — Hygiène des explorateurs, sans effet sur les décisions (TODO §14).

1. Univers crypto : stablecoins (liste et symboles contenant USD ou commençant par EUR), fonds tokenisés
   et symboles que Yahoo ne sert pas (diagnostic du 19/10) sont exclus ; les autres restent ;
2. queue : une entrée par ticker et par jour de Lisbonne. Un ticker analysé puis retiré (ex. USDMXN=X)
   ne revient que le lendemain ; tant qu'il est dans la queue, un meilleur score le met à jour.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_explorateurs_hygiene -v
CoinGecko simulé (liste inventée), queue en dossier temporaire ; aucun réseau.
"""

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

from agents.explorers import queue_manager
from agents.explorers.crypto_explorer import universe

SYMBOLES = ["btc", "usdt", "usds", "usde", "usd1", "rlusd", "eursafo", "buidl", "figr_heloc", "hype", "sui",
            "tao", "wlfi", "link", "pepe", "wbtc"]


class TestUnivers(unittest.TestCase):
    def test_exclusions(self):
        top = [{"symbol": s, "name": s, "market_cap": 1e9, "total_volume": 1e7} for s in SYMBOLES]
        with mock.patch.object(universe, "_fetch_top", return_value=top), \
                mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")):
            self.assertEqual(universe.lister_univers(50), ["BTC-USD", "LINK-USD", "PEPE-USD"])
            self.assertEqual(sorted(universe.metadata_univers(50)), ["BTC-USD", "LINK-USD", "PEPE-USD"])

    def test_regle_stablecoins(self):
        for s in ("USDG", "USDF", "BFUSD", "USDGO", "USYC", "USDY", "EURC"):
            self.assertTrue(universe.est_exclu(s), s)
        for s in ("BTC", "SOL", "SUSHI", "LINK"):
            self.assertFalse(universe.est_exclu(s), s)


class TestQueueDuJour(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(queue_manager, "CHEMIN_QUEUE",
                                         os.path.join(self.dossier.name, "explorer_queue.json"))]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def ajouter(self, ticker="USDMXN=X", score=6):
        return queue_manager.ajouter_decouverte("forex", ticker, score, ["filtre_momentum : RSI 60"])

    def test_une_entree_par_ticker_et_par_jour(self):
        with mock.patch.object(queue_manager, "_jour", return_value="2026-10-20"):
            self.assertTrue(self.ajouter())
            self.assertTrue(self.ajouter(score=8))   # encore dans la queue : meilleur score, mise à jour
            self.assertFalse(self.ajouter(score=8))  # même score : rien
            queue_manager.retirer("USDMXN=X")         # analysé par le tactical
            self.assertFalse(self.ajouter(score=10))  # même jour : ne revient pas
            self.assertTrue(self.ajouter("EURJPY=X"))
        with mock.patch.object(queue_manager, "_jour", return_value="2026-10-21"):
            self.assertTrue(self.ajouter())           # le lendemain
        self.assertEqual(sorted(i["ticker"] for i in queue_manager._lire()), ["EURJPY=X", "USDMXN=X"])

    def test_journal_a_cote_de_la_queue(self):
        self.ajouter()
        self.assertTrue(os.path.isfile(os.path.join(self.dossier.name, "cache", "queue_du_jour.json")))


if __name__ == "__main__":
    unittest.main()
