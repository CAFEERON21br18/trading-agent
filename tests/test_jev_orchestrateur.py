"""
tests/test_jev_orchestrateur.py — Cycle quotidien de bout en bout, avec et sans Jev.

Vrai decider(), analyses et exécution simulées, client Jev simulé : les
décisions transmises au Paper Trader doivent être identiques avec et sans
observateur, et une exception de Jev ne doit pas arrêter la routine.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_orchestrateur -v
Sauté si pandas n'est pas importable (les sous-agents en dépendent) : à lancer sur la tour.
"""

import copy
import os
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")

try:
    import pandas  # noqa: F401
    PANDAS = True
except Exception:
    PANDAS = False

from tests.jev_fixtures import ClientSimule, analyses_exemple


class Stop(Exception):
    """Arrête la routine juste après l'observation (étape 4), sans générer le rapport."""


@unittest.skipUnless(PANDAS, "pandas indisponible sur ce poste : test à lancer sur la tour")
class TestCycleQuotidien(unittest.TestCase):

    def _routine(self, jev_actif: bool, client: ClientSimule) -> list:
        import config
        from utils import database
        from agents import orchestrator as orch
        from agents.jev import observer as obs
        recu = []
        dossier = tempfile.mkdtemp()
        cibles = {
            "init_paper": None, "ouvrir": None, "monitorer_positions": {}, "clore": None,
            "enregistrer_decisions": None, "recuperer_dominance_btc": 50.0, "calculer_correlation": 0.3,
            "recuperer_fear_greed_crypto": {"valeur": 55, "label": "Neutral"},
            "charger_watchlist": {}, "tous_les_tickers": ["BTC-USD", "SPY", "NVDA"],
        }
        patchs = [mock.patch.object(orch, nom, return_value=val) for nom, val in cibles.items()]
        patchs += [
            mock.patch.object(orch, "analyser_actif_complet",
                              side_effect=lambda t, sg=None: {**analyses_exemple(t), "context": dict(sg or {})}),
            mock.patch.object(orch, "executer_ouvertures",
                              side_effect=lambda d: recu.append(copy.deepcopy(d)) or
                              {"ouvertes": [], "refusees": [], "bm_resume": None}),
            mock.patch.object(orch, "enregistrer_snapshot_quotidien", side_effect=Stop),
            mock.patch.object(config, "JEV_OBSERVE", jev_actif),
            mock.patch.object(config, "METACOG_AUDIT_ENABLED", False),
            mock.patch.object(database, "DB_PATH", os.path.join(dossier, "t.db")),
            mock.patch.object(obs, "_contexte_paper", return_value=(set(), "NORMAL", 50.0)),
            mock.patch.object(obs, "_creer_client", return_value=client),
        ]
        for p in patchs:
            p.start()
        try:
            with self.assertRaises(Stop):  # la routine a dépassé l'observation Jev
                orch.generer_rapport_quotidien()
        finally:
            for p in reversed(patchs):
                p.stop()
        return recu

    def test_decision_identique_avec_et_sans_observateur(self):
        sans = self._routine(False, ClientSimule())
        client = ClientSimule(p_acheter=0.99)
        avec = self._routine(True, client)
        self.assertEqual(len(client.states), 3)  # Jev a bien été interrogé
        self.assertEqual(avec, sans)

    def test_exception_jev_ne_casse_pas_le_cycle(self):
        client = ClientSimule(erreur=RuntimeError("panne"))
        sans = self._routine(False, ClientSimule())
        self.assertEqual(self._routine(True, client), sans)


if __name__ == "__main__":
    unittest.main()
