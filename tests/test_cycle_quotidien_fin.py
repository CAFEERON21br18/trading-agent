"""
tests/test_cycle_quotidien_fin.py — Cadre du 17/10/2026, règle 4 : les blocs ajoutés à la fin de
scripts/cycle_daily.py (BLOCS_DE_FIN) passent après toute la routine, et un bloc qui échoue, qui
dépasse son budget ou dont l'import casse ne change rien au cycle : il va jusqu'au bout, avec les
mêmes décisions, le même succès et le même heartbeat. Contrôle des plans : passage de 7h30 seulement.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_cycle_quotidien_fin -v
Routine quotidienne, verrous et heartbeat simulés : sans réseau ni base.
"""

import contextlib
import os
import sys
import time
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

from agents import plans_quotidien
from scripts import cycle_daily

RESUME = {"signaux_detectes": 0, "signaux_forts": 2, "rapport_envoye": True, "alertes_envoyees": 1,
          "alerte_degradation": False}  # décisions de la routine simulée


class BaseCycle(unittest.TestCase):
    def lancer(self, *bloc_patches, routine_effet=None) -> dict:
        """Lance cycle_daily.main() ; rend {code, ordre, routine, succes, heartbeat, duree}."""
        ordre = []
        with contextlib.ExitStack() as pile:
            for nom, valeur in (("_rapport_du_jour_existe", False), ("doit_skipper", (False, "")),
                                ("acquerir_lock", True), ("evaluer_sante", {"ok": True})):
                pile.enter_context(mock.patch.object(cycle_daily, nom, return_value=valeur))
            pile.enter_context(mock.patch.object(cycle_daily, "liberer_lock"))
            succes = pile.enter_context(mock.patch.object(cycle_daily, "signaler_succes"))
            battement = pile.enter_context(mock.patch.object(cycle_daily, "update_heartbeat"))
            pile.enter_context(mock.patch("utils.database.initialiser_base"))
            pile.enter_context(mock.patch("utils.helpers.charger_watchlist", return_value=[]))
            pile.enter_context(mock.patch("utils.collecte_verifiee.collecter_et_verifier",  # collecte réussie
                                          return_value={"ok": True, "raison": ""}))
            routine = pile.enter_context(mock.patch(
                "agents.orchestrator.lancer_routine_quotidienne",
                side_effect=routine_effet or (lambda **k: ordre.append("routine") or dict(RESUME))))
            for _, module, fonction, _ in cycle_daily.BLOCS_DE_FIN:  # chaque bloc simulé, dans l'ordre
                pile.enter_context(mock.patch(f"{module}.{fonction}",
                                              side_effect=lambda f=fonction: ordre.append(f) or 0))
            for p in bloc_patches:
                pile.enter_context(p)
            t0 = time.monotonic()
            code = cycle_daily.main()
            duree = time.monotonic() - t0
        return {"code": code, "ordre": ordre, "routine": routine.call_count, "duree": duree,
                "succes": succes.call_args, "heartbeat": battement.call_args}


class TestBlocsDeFin(BaseCycle):
    def test_apres_la_routine(self):
        r = self.lancer()
        self.assertEqual((r["code"], r["ordre"]),
                         (0, ["routine", "controler_les_plans", "observer_cycle", "synchroniser_du_matin"]))

    def test_chaque_bloc_en_echec_meme_cycle(self):
        temoin = self.lancer()
        for nom, module, fonction, _ in cycle_daily.BLOCS_DE_FIN:
            with self.subTest(bloc=nom):
                r = self.lancer(mock.patch(f"{module}.{fonction}", side_effect=RuntimeError("panne simulée")))
                self.assertEqual(r["code"], 0)
                sans_duree = lambda hb: (hb.args, {k: v for k, v in hb.kwargs.items() if k != "duration_sec"})
                self.assertEqual((r["routine"], r["succes"], sans_duree(r["heartbeat"])),
                                 (1, temoin["succes"], sans_duree(temoin["heartbeat"])))  # mêmes décisions
                self.assertEqual(r["heartbeat"].kwargs["status"], "healthy")

    def test_chaque_bloc_trop_long_le_cycle_n_attend_pas(self):
        lent = [(nom, module, fonction, 0.2) for nom, module, fonction, _ in cycle_daily.BLOCS_DE_FIN]
        for _, module, fonction, _ in lent:
            with self.subTest(bloc=fonction):
                r = self.lancer(mock.patch.object(cycle_daily, "BLOCS_DE_FIN", lent),
                                mock.patch(f"{module}.{fonction}", side_effect=lambda: time.sleep(3)))
                self.assertEqual((r["code"], r["routine"]), (0, 1))
                self.assertLess(r["duree"], 2.0)

    def test_import_casse(self):
        r = self.lancer(mock.patch.object(cycle_daily, "BLOCS_DE_FIN", [("bloc inventé", "module.absent", "f", 5)]))
        self.assertEqual((r["code"], r["routine"]), (0, 1))

    def test_echec_de_la_routine_aucun_bloc(self):
        with mock.patch.object(cycle_daily, "signaler_echec", return_value=1), \
             mock.patch("alerts.channels.email_channel.envoyer_email"):
            r = self.lancer(routine_effet=RuntimeError("routine"))
        self.assertEqual((r["code"], r["ordre"]), (1, []))


class TestPassageDe7h30(unittest.TestCase):
    def controle(self, heure: str):
        h, m = map(int, heure.split(":"))
        moment = datetime(2026, 10, 19, h, m, tzinfo=ZoneInfo("Europe/Lisbon"))
        with mock.patch("agents.plan_advisor.verifier_tous_les_plans", return_value=3) as v:
            return plans_quotidien.controler_les_plans(moment), v.call_count

    def test_matin_seulement(self):
        self.assertEqual(self.controle("07:30"), (3, 1))
        self.assertEqual(self.controle("10:15"), (3, 1))  # 7h30 rattrapé dans la matinée
        self.assertEqual(self.controle("12:00"), (None, 0))
        self.assertEqual(self.controle("12:40"), (None, 0))


if __name__ == "__main__":
    unittest.main()
