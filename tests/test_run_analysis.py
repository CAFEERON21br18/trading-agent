"""
tests/test_run_analysis.py — scripts/run_analysis.py et POST /api/run-analysis.

1. run_analysis --preview : generer_rapport_quotidien rend 3 valeurs (rapport, décisions BUY/SELL
   retenues, toutes les décisions) ; le script les déballe sans erreur et affiche le rapport ;
2. run_analysis sans option : résumé de lancer_routine_quotidienne affiché ;
3. POST /api/run-analysis avec l'en-tête X-AlphaSignal : la vraie lancer_routine_quotidienne tourne
   jusqu'au bout dans son fil, sur un cycle simulé (rapport, décisions, emails, mémoire) ; passage
   « manuel » du registre (R3) ; sans l'en-tête : 403, rien n'est lancé.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_run_analysis -v
Sans réseau, sans base, sans email : tout ce que la routine touche est simulé.
"""

import io
import os
import sys
import threading
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from agents import orchestrator
from dashboard.app import app
from scripts import run_analysis
from utils.registre_manuel import ROUTE_ANALYSE

DECISION = {"decision": {"ticker": "AAA-USD", "decision": "BUY", "confidence": 9, "score_composite": 2.4,
                         "reasoning": "inventé", "convergences": [1], "contradictions": []},
            "analyses": {"technique": {"prix": 100.0},
                         "risque": {"valide": True, "signal": {"stop_loss": 95.0, "target_1": 110.0, "target_2": 120.0}}}}


class TestScript(unittest.TestCase):
    def lancer(self, *options):
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_analysis.py", *options]), redirect_stdout(sortie):
            run_analysis.main()
        return sortie.getvalue()

    def test_preview_trois_valeurs(self):
        with mock.patch.object(run_analysis, "generer_rapport_quotidien",
                               return_value=("# Rapport inventé", [DECISION], [DECISION, {}])):
            sortie = self.lancer("--preview")
        self.assertIn("# Rapport inventé", sortie)
        self.assertIn("1 signaux forts détectés", sortie)

    def test_routine(self):
        resume = {"signaux_forts": 2, "rapport_envoye": False, "alertes_envoyees": 0, "alerte_degradation": False}
        with mock.patch.object(run_analysis, "lancer_routine_quotidienne", return_value=resume) as routine:
            sortie = self.lancer("--no-email")
        routine.assert_called_once_with(envoyer_emails=False)
        self.assertIn("Signaux forts détectés  : 2", sortie)


class TestRoute(unittest.TestCase):
    def setUp(self):
        self.fin, self.resultat = threading.Event(), {}
        vraie = orchestrator.lancer_routine_quotidienne

        def suivie(**kw):  # la vraie routine, observée jusqu'à sa fin
            try:
                self.resultat["resume"] = vraie(**kw)
            except Exception as e:
                self.resultat["erreur"] = e
                raise
            finally:
                self.fin.set()

        pile = ExitStack()
        self.addCleanup(pile.close)
        self.generer = pile.enter_context(mock.patch.object(
            orchestrator, "generer_rapport_quotidien", return_value=("# Rapport inventé", [DECISION], [DECISION])))
        self.signal = pile.enter_context(mock.patch.object(orchestrator, "enregistrer_signal"))
        self.rapport = pile.enter_context(mock.patch.object(orchestrator, "envoyer_rapport_quotidien", return_value=True))
        self.alerte = pile.enter_context(mock.patch.object(orchestrator, "envoyer_alerte_signal_fort", return_value=True))
        for nom, valeur in (("recuperer_fear_greed_crypto", {"valeur": None}), ("mettre_a_jour_performance_md", None),
                            ("verifier_alerte_degradation", (False, ""))):
            pile.enter_context(mock.patch.object(orchestrator, nom, return_value=valeur))
        pile.enter_context(mock.patch.object(orchestrator, "lancer_routine_quotidienne", side_effect=suivie))
        self.client = app.test_client()

    def test_va_jusqu_au_bout(self):
        r = self.client.post("/api/run-analysis", headers={"X-AlphaSignal": "1"})
        self.assertEqual((r.status_code, r.get_json()["started"]), (200, True))
        self.assertTrue(self.fin.wait(10), "la routine n'a pas fini")
        self.assertNotIn("erreur", self.resultat)
        self.assertEqual(self.resultat["resume"], {"signaux_detectes": 0, "signaux_forts": 1, "rapport_envoye": True,
                                                   "alertes_envoyees": 1, "alerte_degradation": False})
        self.generer.assert_called_once_with(ROUTE_ANALYSE)  # registre : passage « manuel »
        self.signal.assert_called_once()
        self.rapport.assert_called_once()

    def test_sans_en_tete_rien_n_est_lance(self):
        self.assertEqual(self.client.post("/api/run-analysis").status_code, 403)
        self.assertFalse(self.fin.wait(0.5))
        self.generer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
