"""
tests/test_daily_routine.py — scripts/daily_routine.py (lancement manuel) : même collecte vérifiée que
cycle_daily (utils/collecte_verifiee.py, REGISTRE_CRITERES v1.9, §9.8 a).

1. Collecte réussie : la routine tourne, code 0 ;
2. collecte en échec : ni routine ni rapport, code 1, échec compté et e-mail d'erreur avec la cause ;
3. chemin réel de la vérification : Yahoo ne répond pas (sonde simulée) → 3 essais à 5 min, puis échec.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_daily_routine -v
Base en dossier temporaire, e-mail et Yahoo simulés ; aucun réseau.
"""

import contextlib
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

from scripts import daily_routine
from utils import database, lock_manager

WATCHLIST = {"crypto": {"AAA-USD": {"timeframes": ["1d"]}}, "stocks": {"BBB": {"timeframes": ["1d"]}}}


class TestDailyRoutine(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.pile = contextlib.ExitStack()
        d = self.dossier.name
        for cible, valeur in (("utils.database.DB_PATH", os.path.join(d, "t.db")),
                              ("utils.lock_manager.LOCK_DIR", d)):
            self.pile.enter_context(mock.patch(cible, valeur))
        self.pile.enter_context(mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")))
        self.pile.enter_context(mock.patch.object(daily_routine, "_rapport_du_jour_existe", return_value=False))
        self.pile.enter_context(mock.patch.object(daily_routine, "evaluer_sante", return_value={"ok": True}))
        self.succes = self.pile.enter_context(mock.patch.object(daily_routine, "signaler_succes"))
        self.echec = self.pile.enter_context(mock.patch.object(daily_routine, "signaler_echec", return_value=1))
        self.email = self.pile.enter_context(mock.patch("alerts.channels.email_channel.envoyer_email"))
        self.routine = self.pile.enter_context(mock.patch(
            "agents.orchestrator.lancer_routine_quotidienne", return_value={"rapport_envoye": True}))

    def tearDown(self):
        self.pile.close()
        self.dossier.cleanup()

    def test_collecte_reussie_routine(self):
        with mock.patch("utils.collecte_verifiee.collecter_et_verifier", return_value={"ok": True, "raison": ""}):
            self.assertEqual(daily_routine.main(), 0)
        self.routine.assert_called_once()
        self.succes.assert_called_once()

    def test_collecte_en_echec_pas_de_routine(self):
        echec = {"ok": False, "raison": "0/23 actifs à jour après 3 essais"}
        with mock.patch("utils.collecte_verifiee.collecter_et_verifier", return_value=echec):
            self.assertEqual(daily_routine.main(), 1)
        self.routine.assert_not_called()
        self.succes.assert_not_called()
        self.assertIn("Collecte des prix en échec", self.echec.call_args.args[0])
        self.assertIn("0/23 actifs à jour", self.email.call_args.kwargs["corps_texte"])

    def test_chemin_reel_trois_essais(self):
        dormir = mock.Mock()
        with mock.patch("utils.helpers.charger_watchlist", return_value=WATCHLIST), \
                mock.patch("utils.collecte_verifiee._sonder", return_value=False), \
                mock.patch("utils.collecte_verifiee._dormir", dormir):
            self.assertEqual(daily_routine.main(), 1)
        self.assertEqual([c.args for c in dormir.call_args_list], [(300,), (300,)])  # 3 essais, 5 min d'écart
        self.routine.assert_not_called()
        self.assertFalse(lock_manager.est_actif("collecte"))  # aucun verrou laissé


if __name__ == "__main__":
    unittest.main()
