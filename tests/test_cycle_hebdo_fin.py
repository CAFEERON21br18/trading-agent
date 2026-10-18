"""
tests/test_cycle_hebdo_fin.py — Règle 4 (cadre du 17/10/2026, repris le 18/10) : les blocs lancés à
la fin de scripts/cycle_weekly.py (BLOCS_APRES_VERROU, carte du code Graphify et vault) passent après
le rapport, l'email, le heartbeat ET la libération du verrou. Un bloc qui échoue, qui dépasse son
budget ou dont l'import casse ne change rien : même rapport, même email, même heartbeat, même code.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_cycle_hebdo_fin -v
Rapport, email, verrous et heartbeat simulés : sans réseau, sans base, sans Graphify.
"""

import contextlib
import os
import sys
import time
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from scripts import cycle_weekly

RAPPORT = "# Rapport hebdomadaire inventé\n"


class TestBlocsApresVerrou(unittest.TestCase):
    def lancer(self, *patches, rapport_effet=None) -> dict:
        """Lance cycle_weekly.main() ; rend {code, ordre, emails, heartbeat, duree}."""
        ordre = []
        with contextlib.ExitStack() as pile:
            pile.enter_context(mock.patch.object(cycle_weekly, "doit_skipper", return_value=(False, "")))
            pile.enter_context(mock.patch.object(cycle_weekly, "acquerir_lock", return_value=True))
            pile.enter_context(mock.patch.object(cycle_weekly, "liberer_lock",
                                                 side_effect=lambda c: ordre.append("verrou libéré")))
            battement = pile.enter_context(mock.patch.object(cycle_weekly, "update_heartbeat"))
            pile.enter_context(mock.patch.object(
                cycle_weekly, "_generer_rapport_hebdo",
                side_effect=rapport_effet or (lambda: ordre.append("rapport") or RAPPORT)))
            email = pile.enter_context(mock.patch("alerts.channels.email_channel.envoyer_email",
                                                  side_effect=lambda **k: ordre.append("email") or True))
            for _, module, fonction, _ in cycle_weekly.BLOCS_APRES_VERROU:  # blocs simulés, dans l'ordre
                pile.enter_context(mock.patch(f"{module}.{fonction}",
                                              side_effect=lambda f=fonction: ordre.append(f) or {}))
            for p in patches:
                pile.enter_context(p)
            t0 = time.monotonic()
            code = cycle_weekly.main()
            duree = time.monotonic() - t0
        return {"code": code, "ordre": ordre, "emails": email.call_args_list,
                "heartbeat": battement.call_args, "duree": duree}

    @staticmethod
    def sans_duree(hb):
        return hb.args, {k: v for k, v in hb.kwargs.items() if k != "duration_sec"}

    def test_apres_le_verrou(self):
        r = self.lancer()
        self.assertEqual(r["code"], 0)
        self.assertEqual(r["ordre"], ["rapport", "email", "verrou libéré", "regenerer"])

    def test_chaque_bloc_en_echec_meme_cycle(self):
        temoin = self.lancer()
        for nom, module, fonction, _ in cycle_weekly.BLOCS_APRES_VERROU:
            with self.subTest(bloc=nom):
                r = self.lancer(mock.patch(f"{module}.{fonction}", side_effect=RuntimeError("panne simulée")))
                self.assertEqual(r["code"], 0)
                self.assertEqual(r["ordre"], ["rapport", "email", "verrou libéré"])
                self.assertEqual(r["emails"], temoin["emails"])  # même rapport envoyé
                self.assertEqual(self.sans_duree(r["heartbeat"]), self.sans_duree(temoin["heartbeat"]))
                self.assertEqual(r["heartbeat"].kwargs["status"], "healthy")

    def test_chaque_bloc_trop_long_le_cycle_n_attend_pas(self):
        lent = [(nom, module, fonction, 0.2) for nom, module, fonction, _ in cycle_weekly.BLOCS_APRES_VERROU]
        for _, module, fonction, _ in lent:
            with self.subTest(bloc=fonction):
                r = self.lancer(mock.patch.object(cycle_weekly, "BLOCS_APRES_VERROU", lent),
                                mock.patch(f"{module}.{fonction}", side_effect=lambda: time.sleep(3)))
                self.assertEqual(r["code"], 0)
                self.assertEqual(r["ordre"][:3], ["rapport", "email", "verrou libéré"])
                self.assertLess(r["duree"], 2.0)

    def test_import_casse(self):
        r = self.lancer(mock.patch.object(cycle_weekly, "BLOCS_APRES_VERROU",
                                          [("bloc inventé", "module.absent", "f", 5)]))
        self.assertEqual((r["code"], r["ordre"]), (0, ["rapport", "email", "verrou libéré"]))

    def test_lancement_impossible(self):
        r = self.lancer(mock.patch("utils.bloc_borne.lancer_blocs", side_effect=RuntimeError("cassé")))
        self.assertEqual(r["code"], 0)

    def test_echec_du_rapport_code_inchange(self):
        r = self.lancer(rapport_effet=RuntimeError("rapport"))
        self.assertEqual(r["code"], 1)
        self.assertEqual(r["heartbeat"].kwargs["status"], "error")
        self.assertEqual(r["ordre"], ["verrou libéré", "regenerer"])  # la carte ne dépend pas du rapport

    def test_cycle_saute_aucun_bloc(self):
        with mock.patch.object(cycle_weekly, "doit_skipper", return_value=(True, "daily en cours")), \
                mock.patch.object(cycle_weekly, "update_heartbeat"), \
                mock.patch("scripts.regenerer_graphe.regenerer") as regen:
            self.assertEqual(cycle_weekly.main(), 0)
        regen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
