"""
tests/test_cycles_explorateurs.py — TODO §18 et §19 : le stratégique ne lance plus les explorateurs et
ne lit pas la queue ; le tactical lance toujours les 7 explorateurs, qui alimentent la queue.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_cycles_explorateurs -v
Univers et filtres des explorateurs simulés (tickers inventés), queue dans un dossier temporaire,
verrous, heartbeat, registre, conseiller et régime simulés : sans réseau ni base.
"""

import contextlib
import importlib
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

from agents.explorers import queue_manager
from scripts import cycle_strategic, cycle_tactical

EXPLORATEURS = [("agents.explorers.crypto_explorer.explorer", "CryptoExplorer"),
                ("agents.explorers.stock_explorer.explorer", "StockExplorer"),
                ("agents.explorers.index_explorer.explorer", "IndexExplorer"),
                ("agents.explorers.etf_explorer.explorer", "ETFExplorer"),
                ("agents.explorers.commodity_explorer.explorer", "CommodityExplorer"),
                ("agents.explorers.forex_explorer.explorer", "ForexExplorer"),
                ("agents.explorers.cfd_index_explorer.explorer", "CFDIndexExplorer")]


def classes():
    return [getattr(importlib.import_module(m), c) for m, c in EXPLORATEURS]


class TestTactical(unittest.TestCase):
    def test_lance_les_7_explorateurs_qui_alimentent_la_queue(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as pile:
            chemin = os.path.join(d, "explorer_queue.json")
            pile.enter_context(mock.patch.object(queue_manager, "CHEMIN_QUEUE", chemin))
            pile.enter_context(mock.patch("agents.explorers.base.update_heartbeat_explorer"))
            courriel = pile.enter_context(mock.patch("agents.explorers.base.envoyer_email"))
            for i, cls in enumerate(classes()):
                pile.enter_context(mock.patch.object(cls, "universe", lambda self, i=i: [f"ZZ{i}-INVENTE"]))
                pile.enter_context(mock.patch.object(cls, "appliquer_filtres",
                                                     lambda self, t: (5, ["filtre inventé"], {})))
            decouvertes, observations = cycle_tactical._lancer_explorateurs()
            with open(chemin, encoding="utf-8") as f:
                queue = json.load(f)
        self.assertEqual((decouvertes, observations), (0, 7))  # score 5 : en queue (≥ 4), observation (< 6)
        self.assertEqual(sorted(e["ticker"] for e in queue), [f"ZZ{i}-INVENTE" for i in range(7)])
        courriel.assert_not_called()  # alerte email seulement à partir de 7


class TestStrategique(unittest.TestCase):
    def test_tourne_sans_explorateur_ni_queue(self):
        battements = []
        with contextlib.ExitStack() as pile:
            scanners = [pile.enter_context(mock.patch.object(c, "scanner", side_effect=AssertionError("interdit")))
                        for c in classes()]
            pile.enter_context(mock.patch.object(queue_manager, "lire_queue", side_effect=AssertionError("interdit")))
            for nom, valeur in (("doit_skipper", (False, "")), ("acquerir_lock", True), ("ouvrir", object())):
                pile.enter_context(mock.patch.object(cycle_strategic, nom, return_value=valeur))
            pile.enter_context(mock.patch.object(cycle_strategic, "liberer_lock"))
            pile.enter_context(mock.patch.object(cycle_strategic, "clore"))
            pile.enter_context(mock.patch.object(cycle_strategic, "update_heartbeat",
                                                 side_effect=lambda *a, **k: battements.append((a, k))))
            pile.enter_context(mock.patch("utils.portfolio_db.initialiser_paper_db"))
            monitor = pile.enter_context(mock.patch("agents.paper_trader.monitor.monitorer_positions"))
            pile.enter_context(mock.patch("agents.real_advisor.evaluer_tout_le_portefeuille", return_value=2))
            pile.enter_context(mock.patch("utils.real_portfolio_db.initialiser_real_db"))
            pile.enter_context(mock.patch("agents.technical_skills.market_regime.detecter_regime_global",
                                          return_value={"regime_global": "range", "mode": "neutre"}))
            pile.enter_context(mock.patch("agents.technical_skills.market_regime.detecter_regime_actif",
                                          return_value={"regime": "indispo"}))
            pile.enter_context(mock.patch("agents.technical_skills.market_regime.enregistrer_regime"))
            code = cycle_strategic.main()
        self.assertEqual(code, 0)
        monitor.assert_called_once()
        self.assertTrue(all(not s.called for s in scanners))
        (cycle, *_), extra = battements[-1][0], battements[-1][1]
        self.assertEqual((cycle, extra["status"]), ("strategic", "healthy"))
        self.assertEqual(set(extra["extra"]), {"conseils_reels", "regime_global"})

    def test_source_sans_explorateur(self):
        with open(os.path.join(RACINE, "scripts", "cycle_strategic.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("agents.explorers", source)
        self.assertNotIn("lire_queue", source)


if __name__ == "__main__":
    unittest.main()
