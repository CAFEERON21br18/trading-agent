"""
tests/test_sources_passage.py — Sources d'état manquantes de la page Architecture : les 12 composants sans
source (7 explorateurs, queue, Market Analyst, Risk Manager, Knowledge, Groq) écrivent une
ligne INFO par passage (utils/passage.noter_passage), au format que lit dashboard/api/etat_journaux.py.

Bout en bout : le vrai code de chaque composant tourne (données, heartbeat et queue simulés), ses lignes
sont écrites au format de utils/logger dans un tactical.log temporaire, puis lues par etat_composants :
chacun passe de « pas de source d'état » à « actif ». Une seule ligne par composant et par processus.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_sources_passage -v
Sans réseau ni base : tout est simulé, logs dans un dossier temporaire.
"""

import importlib
import logging
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest import mock

import numpy as np
import pandas as pd

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.api import etat_composants, topology_composants as tc
from utils import logger as journal, passage

SANS_SOURCE = ["explorer.crypto", "explorer.stock", "explorer.index", "explorer.etf", "explorer.commodity",
               "explorer.forex", "explorer.cfd_index", "queue", "analyst.market", "risk_manager", "knowledge",
               "llm.groq"]


def carte_du_depot() -> dict:
    """Composants de la carte avec leurs modules (règles de topology_composants), sans Graphify."""
    modules = {}
    for racine, dossiers, fichiers in os.walk(RACINE):
        dossiers[:] = [d for d in dossiers if d not in (".git", ".venv", "graphify-out", "tests", "__pycache__")]
        for f in fichiers:
            if f.endswith(".py"):
                chemin = os.path.relpath(os.path.join(racine, f), RACINE).replace("\\", "/")
                modules.setdefault(tc.composant(chemin), []).append(chemin)
    noeuds = [{"id": c, "libelle": l, "groupe": g, "type": "composant",
               "modules": [{"chemin": m, "tags": []} for m in modules.get(c, [])]} for c, (l, g, _) in tc.COMPOSANTS.items()]
    return {"noeuds": noeuds, "sources_etat": {"taches": {"cycle.tactical": ["tactical"]}, "tables_inserees": {},
                                               "modules_journalises": []}}


def faire_tourner_les_composants():
    """Le vrai code instrumenté de chacun des 13 composants, sans données ni écriture."""
    with ExitStack() as pile:
        pile.enter_context(mock.patch("agents.explorers.base.update_heartbeat_explorer"))
        for nom in ("crypto", "stock", "index", "etf", "commodity", "forex", "cfd_index"):
            module = importlib.import_module(f"agents.explorers.{nom}_explorer.explorer")
            classe = next(v for v in vars(module).values() if isinstance(v, type) and v.__module__ == module.__name__)
            pile.enter_context(mock.patch.object(classe, "universe", return_value=[]))
            classe().scanner()
        from agents.explorers import queue_manager
        pile.enter_context(mock.patch.object(queue_manager, "_lire", return_value=[]))
        queue_manager.lire_queue()
        from agents.analysts.market_analyst.patterns import detecter_tous_patterns
        prix = 100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 120))
        detecter_tous_patterns(pd.DataFrame({"open": prix, "high": prix + 1, "low": prix - 1, "close": prix,
                                             "volume": 1000.0}))
        from agents.analysts.risk_manager.position_sizer import calculer_stop_loss
        calculer_stop_loss(100.0, "LONG", 2.0)
        from agents.knowledge import chart_reading
        pile.enter_context(mock.patch.object(chart_reading, "charger_ohlcv", return_value=pd.DataFrame()))
        chart_reading.analyser_graphique("AAA")
        from utils.groq_appels import noter_appel
        noter_appel("modele-test", True)


class TestSourcesPassage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        for nom in ("tactical.log", "tactical_errors.log"):
            open(os.path.join(self.d.name, nom), "w").close()
        passage._derniers.clear()

    def journaliser(self, action):
        """Toutes les lignes émises pendant action(), au format de utils/logger, dans tactical.log."""
        handler = logging.FileHandler(os.path.join(self.d.name, "tactical.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter(journal.LOG_FORMAT, datefmt=journal.DATE_FORMAT))
        racine = logging.getLogger()
        racine.addHandler(handler)
        try:
            logging.getLogger("cycle_tactical").info("🟡 CYCLE TACTIQUE v4.1 — démarrage")
            with mock.patch.object(sys, "stderr"):
                action()
        finally:
            racine.removeHandler(handler)
            handler.close()

    def etats(self):
        with mock.patch.object(etat_composants.etat_taches, "lire_taches", return_value={}):
            r = etat_composants.etat_des_composants(carte_du_depot(), datetime.now(timezone.utc),
                                                    dossier_logs=self.d.name, bases={})
        return {c: r["composants"][c]["etat"] for c in SANS_SOURCE}

    def test_de_pas_de_source_a_actif(self):
        self.journaliser(lambda: None)
        self.assertEqual(set(self.etats().values()), {"pas de source d'état"})  # avant : rien dans les logs
        self.journaliser(faire_tourner_les_composants)
        self.assertEqual(self.etats(), {c: "actif" for c in SANS_SOURCE})

    def test_une_ligne_par_processus(self):
        self.journaliser(lambda: (faire_tourner_les_composants(), faire_tourner_les_composants()))
        with open(os.path.join(self.d.name, "tactical.log"), encoding="utf-8") as f:
            lignes = [l for l in f if ": passage" in l]
        self.assertEqual(len(lignes), len(SANS_SOURCE))
        self.assertTrue(all(" | INFO     | " in l for l in lignes))

    def test_noter_passage_ne_leve_jamais(self):
        cassé = mock.Mock(name="logger")
        cassé.info.side_effect = OSError("disque plein")
        passage.noter_passage(cassé, "Composant")


if __name__ == "__main__":
    unittest.main()
