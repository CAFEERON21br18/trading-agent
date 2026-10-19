"""
tests/test_collecte_verifiee.py — Collecte des prix vérifiée et relancée (REGISTRE_CRITERES v1.9, §9.8 a).

1. Collecte vide (diagnostic du 17/10) : 3 essais à 5 min d'intervalle, puis le cycle quotidien
   n'exécute pas la routine et n'écrit pas le rapport du jour (le rattrapage de 12h retentera) ;
2. collecte partielle à 50 % : nouvel essai ; à 100 % au 2e essai, succès ;
3. date attendue (crypto : le jour ; autres : la dernière séance de semaine) ; jour férié toléré
   (téléchargement non vide sans barre du jour) ; sonde en échec : pas de collecte complète ;
4. filet du tactical : déclenché si la dernière barre 1d a été écrite il y a plus de 30 h, une
   seule fois par heure, jamais pendant le cycle quotidien.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_collecte_verifiee -v
Base, verrous et état du filet en dossier temporaire ; aucun appel à Yahoo (tout est simulé).
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import collecte_verifiee as cv, database, lock_manager
from scripts import cycle_daily
from tests.test_cycle_quotidien_fin import BaseCycle

MERCREDI = datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc)
WATCHLIST = {"crypto": {f"C{i}-USD": {"timeframes": ["1d"]} for i in range(4)},
             "stocks": {f"S{i}": {"timeframes": ["1d", "1wk"]} for i in range(6)}}
TICKERS = [t for v in WATCHLIST.values() for t in v]


class BaseCollecte(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        d = self.dossier.name
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(d, "t.db")),
                       mock.patch.object(lock_manager, "LOCK_DIR", d),
                       mock.patch.object(cv, "ETAT_FILET", os.path.join(d, "filet.json")),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))]
        for p in self.patchs:
            p.start()
        database.initialiser_base()
        for t in TICKERS:  # barres périmées : la dernière date du 15/10, écrite il y a 40 h
            self.barre(t, date(2026, 10, 15), "2026-10-19 14:30:00")

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def barre(self, ticker, jour, ecrite):
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO prices (ticker, timeframe, timestamp, open, high, low, close, volume, "
                     "created_at) VALUES (?, '1d', ?, 1, 1, 1, 1, 1, ?)", (ticker, f"{jour} 00:00:00", ecrite))
        conn.commit()
        conn.close()

    def collecte_partielle(self, part):
        """Fausse collecte : écrit la barre attendue pour `part` des actifs, téléchargement vide ailleurs."""
        n = round(len(TICKERS) * part)

        def collecter(watchlist):
            for t in TICKERS[:n]:
                self.barre(t, cv.date_attendue(t, MERCREDI), "2026-10-21 06:30:00")
            return {t: {"1d": (1 if i < n else None)} for i, t in enumerate(TICKERS)}
        return mock.Mock(side_effect=collecter)

    def lancer(self, collecter, sonder=lambda w: True):
        dormir = mock.Mock()
        r = cv.collecter_et_verifier(charger=lambda: WATCHLIST, collecter=collecter, sonder=sonder,
                                     dormir=dormir, maintenant=lambda: MERCREDI)
        return r, dormir


class TestCollecteVerifiee(BaseCollecte):
    def test_collecte_vide_trois_essais_puis_echec(self):
        collecter = self.collecte_partielle(0)
        r, dormir = self.lancer(collecter)
        self.assertEqual((r["ok"], r["essais"], collecter.call_count), (False, 3, 3))
        self.assertEqual([c.args for c in dormir.call_args_list], [(300,), (300,)])  # 5 min entre les essais
        self.assertIn("0/10 actifs à jour", r["raison"])

    def test_collecte_partielle_nouvel_essai(self):
        etapes = [self.collecte_partielle(0.5), self.collecte_partielle(1.0)]
        collecter = mock.Mock(side_effect=lambda w: etapes[collecter.call_count - 1](w))
        r, dormir = self.lancer(collecter)
        self.assertEqual((r["ok"], r["essais"], dormir.call_count), (True, 2, 1))

    def test_succes_du_premier_coup(self):
        r, dormir = self.lancer(self.collecte_partielle(1.0))
        self.assertEqual((r["ok"], r["essais"], r["part"]), (True, 1, 1.0))
        dormir.assert_not_called()

    def test_date_attendue_et_jour_ferie(self):
        lundi = datetime(2026, 10, 19, 6, 30, tzinfo=timezone.utc)
        self.assertEqual(cv.date_attendue("C0-USD", lundi), date(2026, 10, 19))
        self.assertEqual(cv.date_attendue("S0", lundi), date(2026, 10, 16))  # vendredi
        # téléchargement non vide sans barre du jour (marché fermé) : l'actif compte comme à jour
        v = cv.verifier(WATCHLIST, {t: {"1d": 0} for t in TICKERS}, MERCREDI)
        self.assertEqual(v["part"], 1.0)

    def test_sonde_en_echec_pas_de_collecte_complete(self):
        collecter = self.collecte_partielle(1.0)
        r, _ = self.lancer(collecter, sonder=lambda w: False)
        self.assertEqual((r["ok"], collecter.call_count), (False, 0))


class TestCycleQuotidien(BaseCycle):
    def test_collecte_en_echec_pas_de_routine_ni_de_rapport(self):
        echec = {"ok": False, "essais": 3, "raison": "0/23 actifs à jour après 3 essais"}
        with mock.patch.object(cycle_daily, "signaler_echec", return_value=1) as signal:
            r = self.lancer(mock.patch("utils.collecte_verifiee.collecter_et_verifier", return_value=echec))
        self.assertEqual((r["code"], r["routine"], r["ordre"]), (1, 0, []))  # ni routine, ni rapport, ni blocs
        self.assertIn("collecte des prix", signal.call_args.args[0])
        self.assertEqual(r["heartbeat"].kwargs["status"], "error")


class TestFiletTactical(BaseCollecte):
    def filet(self, maintenant, collecter):
        return cv.filet_tactical(charger=lambda: WATCHLIST, collecter=collecter, sonder=lambda w: True,
                                 maintenant=lambda: maintenant)

    def test_une_seule_fois_par_heure(self):
        collecter = mock.Mock(return_value={})
        t0 = datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc)  # dernière écriture il y a 40 h
        self.assertEqual(self.filet(t0, collecter), "relancee")
        self.assertEqual(self.filet(t0 + timedelta(minutes=15), collecter), "attente")
        self.assertEqual(self.filet(t0 + timedelta(minutes=45), collecter), "attente")
        self.assertEqual(collecter.call_count, 1)
        self.assertEqual(self.filet(t0 + timedelta(minutes=61), collecter), "relancee")
        self.assertEqual(collecter.call_count, 2)

    def test_inutile_si_barre_recente_et_jamais_pendant_le_quotidien(self):
        collecter = mock.Mock(return_value={})
        recent = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)  # écrite il y a 21 h 30
        self.assertEqual(self.filet(recent, collecter), "inutile")
        self.assertTrue(lock_manager.acquerir_lock("daily"))
        self.assertEqual(self.filet(datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc), collecter),
                         "quotidien en cours")
        lock_manager.liberer_lock("daily")
        collecter.assert_not_called()

    def test_verrou_collecte_pris(self):
        self.assertTrue(lock_manager.acquerir_lock(cv.VERROU))  # le cycle quotidien collecte
        collecter = mock.Mock(return_value={})
        self.assertEqual(self.filet(datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc), collecter), "verrou pris")
        collecter.assert_not_called()
        lock_manager.liberer_lock(cv.VERROU)


if __name__ == "__main__":
    unittest.main()
