"""
tests/test_alerte_routine.py — Alerte « journée sans routine » (collectes de 7h30 et de 12h en échec).

1. Avant midi (Lisbonne) : aucun e-mail, le rattrapage de 12h retentera ;
2. après midi : UN e-mail par jour, avec la cause journalisée ; le lendemain, de nouveau ;
3. un e-mail en échec ne lève pas et n'est pas compté comme envoyé ;
4. cycle quotidien : collecte en échec à 12h35 → un e-mail, ni routine ni rapport.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_alerte_routine -v
E-mail simulé, état en dossier temporaire ; aucun réseau.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import alerte_routine
from tests.test_cycle_quotidien_fin import BaseCycle

LIS = ZoneInfo("Europe/Lisbon")
CAUSE = "0/23 actifs à jour après 3 essais (seuil 80 %) ; manquants : BTC-USD, ETH-USD"


def heure(jour, h, m=0):
    return datetime(2026, 10, jour, h, m, tzinfo=LIS)


class BaseAlerte(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(alerte_routine, "ETAT", os.path.join(self.dossier.name, "alerte.json")),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()


class TestAlerte(BaseAlerte):
    def test_avant_midi_rien(self):
        envoyer = mock.Mock()
        self.assertFalse(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(22, 7, 40), envoyer))
        envoyer.assert_not_called()

    def test_un_seul_email_par_jour(self):
        envoyer = mock.Mock()
        self.assertTrue(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(22, 12, 40), envoyer))
        self.assertFalse(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(22, 13, 10), envoyer))
        self.assertEqual(envoyer.call_count, 1)
        kwargs = envoyer.call_args.kwargs
        self.assertEqual(kwargs["sujet"], alerte_routine.SUJET)
        self.assertIn("Collecte des prix en échec, pas de routine ni d'observation Jev aujourd'hui", kwargs["corps_texte"])
        self.assertIn(CAUSE, kwargs["corps_texte"])
        self.assertTrue(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(23, 12, 5), envoyer))  # lendemain
        self.assertEqual(envoyer.call_count, 2)

    def test_email_en_echec(self):
        panne = mock.Mock(side_effect=OSError("SMTP injoignable"))
        self.assertFalse(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(22, 12, 40), panne))
        envoyer = mock.Mock()  # pas compté comme envoyé : le passage suivant réessaie
        self.assertTrue(alerte_routine.alerter_journee_sans_routine(CAUSE, heure(22, 12, 50), envoyer))


class TestCycleQuotidien(BaseCycle, BaseAlerte):
    def setUp(self):
        BaseAlerte.setUp(self)

    def tearDown(self):
        BaseAlerte.tearDown(self)

    def test_rattrapage_en_echec_un_email(self):
        echec = {"ok": False, "essais": 3, "raison": CAUSE}
        reelle = alerte_routine.alerter_journee_sans_routine  # le montage commun la simule : on la rétablit
        with mock.patch("alerts.channels.email_channel.envoyer_email") as email, \
                mock.patch.object(alerte_routine, "_maintenant", return_value=heure(22, 12, 35)):
            r = self.lancer(mock.patch("utils.collecte_verifiee.collecter_et_verifier", return_value=echec),
                            mock.patch("scripts.cycle_daily.signaler_echec", return_value=1),
                            mock.patch.object(alerte_routine, "alerter_journee_sans_routine", reelle))
            r2 = self.lancer(mock.patch("utils.collecte_verifiee.collecter_et_verifier", return_value=echec),
                             mock.patch("scripts.cycle_daily.signaler_echec", return_value=2),
                             mock.patch.object(alerte_routine, "alerter_journee_sans_routine", reelle))
        self.assertEqual((r["code"], r["routine"], r2["code"], r2["routine"]), (1, 0, 1, 0))
        self.assertEqual(email.call_count, 1)  # un seul e-mail pour la journée
        self.assertEqual(email.call_args.kwargs["sujet"], alerte_routine.SUJET)


if __name__ == "__main__":
    unittest.main()
