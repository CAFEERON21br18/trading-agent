"""
tests/test_jev_observer.py — Observation Jev : sans réseau, sans clé (client simulé).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_observer -v
Base SQLite temporaire. Le test de bout en bout de l'orchestrateur est sauté si
pandas n'est pas importable (poste sans dépendances des cycles) : il tourne sur la tour.
"""

import ast
import copy
import glob
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

import config
from utils import database
from agents.jev import observer as obs
from agents.jev.questions import niveau_conviction, taille_hypothetique
from agents.jev.state import construire_state, serialiser
from tests.jev_fixtures import (SECRET_LECON, SECRET_PATTERN, SECRET_REEL, ClientSimule,
                                analyses_exemple, decisions_exemple)

class BaseTemp(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "t.db")),
                       mock.patch.object(config, "JEV_OBSERVE", True),
                       mock.patch.object(config, "TYPESAFE_API_KEY", ""),
                       mock.patch.object(obs, "_contexte_paper", return_value=({"SPY"}, "NORMAL", 50.0))]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def lignes(self) -> list[dict]:
        from utils.jev_db import connexion_lecture, lire
        conn = connexion_lecture()
        try:
            return lire(conn)
        finally:
            conn.close()


class TestState(unittest.TestCase):
    """Le state ne contient ni portefeuille réel, ni texte libre de memory/*.md, ni décision."""

    def test_liste_blanche(self):
        texte = serialiser(construire_state("BTC-USD", analyses_exemple(), False))
        for secret in (SECRET_LECON, SECRET_PATTERN, SECRET_REEL):
            self.assertNotIn(secret, texte)
        state = construire_state("BTC-USD", analyses_exemple(), True)
        self.assertEqual(set(state), {"ticker", "position_paper_ouverte", "technique", "fondamental",
                                      "sentiment", "risque", "context", "memoire_paper"})
        self.assertEqual(state["memoire_paper"], {"trades": 4, "winrate_pct": 50.0})
        self.assertEqual(state["position_paper_ouverte"], "oui")
        self.assertNotIn("decision", texte.lower().replace("decision_", ""))

    def test_aucun_import_du_portefeuille_reel(self):
        for chemin in glob.glob(os.path.join(RACINE, "agents", "jev", "*.py")):
            with open(chemin, encoding="utf-8") as f:
                imports = [l for l in f if re.match(r"\s*(from|import)\s", l)]
            self.assertFalse([l for l in imports if "real" in l], chemin)

    def test_state_envoye_identique_au_state_controle(self):
        client = ClientSimule()
        with mock.patch.object(database, "DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db")), \
                mock.patch.object(config, "JEV_OBSERVE", True), \
                mock.patch.object(obs, "_contexte_paper", return_value=(set(), None, None)):
            obs.observer(obs.preparer_observations(decisions_exemple()[:1], "quotidien"), client=client)
        self.assertEqual(client.states, [serialiser(construire_state("BTC-USD", analyses_exemple(), False))])


class TestInterrupteur(BaseTemp):
    def test_rien_ne_part_sans_jev_observe(self):
        client = ClientSimule()
        with mock.patch.object(config, "JEV_OBSERVE", False), \
                mock.patch.object(obs, "_creer_client") as creer:
            self.assertEqual(obs.preparer_observations(decisions_exemple(), "quotidien"), [])
            obs.observer([{"ticker": "X", "state": "{}"}], client=client)
            creer.assert_not_called()
        self.assertEqual(client.states, [])
        self.assertFalse(os.path.exists(database.DB_PATH))  # pas même une table créée

    def test_ni_manuel_ni_tactical(self):
        self.assertEqual(obs.preparer_observations(decisions_exemple(), "manuel"), [])
        self.assertEqual(obs.preparer_observations(decisions_exemple(), "tactical"), [])

    def test_sans_cle_aucun_appel(self):
        resume = obs.observer(obs.preparer_observations(decisions_exemple(), "quotidien"))
        self.assertEqual(resume["appels"], 0)


class TestRobustesse(BaseTemp):
    def test_exception_jev_journalisee_et_ignoree(self):
        for erreur in (TimeoutError("3 s"), RuntimeError("réseau"), KeyError("action")):
            resume = obs.observer(obs.preparer_observations(decisions_exemple(), "quotidien"),
                                  client=ClientSimule(erreur=erreur))
            self.assertEqual(resume["erreurs"], 3)
        self.assertEqual({l["statut"] for l in self.lignes()}, {"erreur"})

    def test_erreurs_internes_ne_remontent_pas(self):
        self.assertEqual(obs.preparer_observations([{"cassé": True}], "quotidien"), [])
        with mock.patch.object(obs, "construire_questions", side_effect=ImportError("sdk")):
            obs.observer([{"ticker": "X", "state": "{}"}], client=ClientSimule())
        with mock.patch("utils.jev_db.inserer", side_effect=OSError("disque")):
            resume = obs.observer(obs.preparer_observations(decisions_exemple(), "quotidien"),
                                  client=ClientSimule())
        self.assertEqual(resume["ok"], 3)

    def test_decisions_non_modifiees(self):
        decisions = decisions_exemple()
        avant = copy.deepcopy(decisions)
        lot = obs.preparer_observations(decisions, "quotidien")
        obs.observer(lot, client=ClientSimule(p_acheter=0.99))
        self.assertEqual(decisions, avant)


class TestEnregistrement(BaseTemp):
    def test_ligne_complete(self):
        obs.observer(obs.preparer_observations(decisions_exemple(), "quotidien"), client=ClientSimule())
        lignes = {l["ticker"]: l for l in self.lignes()}
        btc, spy = lignes["BTC-USD"], lignes["SPY"]
        self.assertEqual((btc["statut"], btc["modele"], btc["decision_moteur"]), ("ok", "jev-1.13.0", "BUY"))
        self.assertEqual((btc["position_ouverte"], spy["position_ouverte"]), (0, 1))
        self.assertAlmostEqual(btc["p_acheter"], 0.7)
        self.assertEqual((btc["conviction_niveau"], btc["taille_hypothetique"]), (2, 40.0))  # 0.5 × 80
        self.assertEqual((btc["jetons_entree"], btc["regime_jev"], btc["regime_moteur"]),
                         (120, "haussier", "haussier"))

    def test_budget_et_ordre_tire_au_sort(self):
        temps = iter(range(0, 1000, 50))  # chaque lecture d'horloge avance de 50 s
        resume = obs.observer(obs.preparer_observations(decisions_exemple(), "quotidien"),
                              client=ClientSimule(), horloge=lambda: next(temps))
        self.assertEqual(resume["appels"] + len(resume["ecartes"]), 3)
        self.assertTrue(resume["ecartes"])
        self.assertEqual(sum(1 for l in self.lignes() if l["statut"] == "ecarte"), len(resume["ecartes"]))

    def test_conviction(self):
        self.assertEqual(niveau_conviction({"0": 0.4, "1": 0.4, "2": 0.2}), 0)  # égalité → plus bas
        self.assertIsNone(taille_hypothetique(3, None, 50.0))
        self.assertEqual(taille_hypothetique(3, 80.0, 50.0), 50.0)  # plafond du Budget Manager


class TestBranchement(unittest.TestCase):
    """orchestrator.py : préparation avant l'exécution paper, observation après, sortie jamais lue."""

    def test_structure(self):
        with open(os.path.join(RACINE, "agents", "orchestrator.py"), encoding="utf-8") as f:
            source = f.read()
        arbre = ast.parse(source)
        appels = {n.func.id: n.lineno for n in ast.walk(arbre)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertLess(appels["decider"], appels["preparer_observations"])
        self.assertLess(appels["preparer_observations"], appels["executer_ouvertures"])
        self.assertLess(appels["executer_ouvertures"], appels["observer_jev"])
        self.assertEqual(source.count("jev_lot"), 2)  # affecté une fois, passé une fois à observer_jev
        self.assertRegex(source, r"\n    observer_jev\(jev_lot\)")  # résultat non affecté
        for chemin in ("scripts/cycle_tactical.py", "agents/real_advisor.py", "agents/decision_engine.py"):
            with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
                self.assertNotIn("jev", f.read().lower(), chemin)


if __name__ == "__main__":
    unittest.main()
