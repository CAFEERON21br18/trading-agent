"""
tests/test_etat_sources.py — Phase 3, vue temps réel : lecteurs des sources d'état (lecture seule).
- etat_journaux : passages (lignes « démarrage »), loggers, dernière ERROR, fichiers écartés
  (task_*.log, anciens journaux sans _errors), sauvegarde .1, cache ;
- etat_taches : sortie de PowerShell simulée (aucun appel réel), période des déclencheurs, échec → None ;
- etat_tables : dernière ligne, lignes et passages des 24 h, colonne erreur, base intacte (mode=ro).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_etat_sources -v
Données inventées, dossiers temporaires.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.api import etat_journaux, etat_tables, etat_taches

MAINTENANT = datetime.now().replace(microsecond=0)
H = lambda heures: (MAINTENANT - timedelta(hours=heures)).strftime("%Y-%m-%d %H:%M:%S")
L = lambda h, niveau, nom, msg: f"{H(h)} | {niveau:<8} | {nom} | {msg}\n"
SENT = "agents.analysts.sentiment_analyst.news_fetcher"


def ecrire(dossier, nom, lignes):
    with open(os.path.join(dossier, nom), "w", encoding="utf-8") as f:
        f.writelines(lignes)


class TestJournaux(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        etat_journaux._cache.clear()
        ecrire(self.d.name, "tactical.log", [
            L(30, "INFO", "cycle_tactical", "🟡 CYCLE TACTIQUE v4.1 — démarrage"),
            L(29.9, "INFO", "agents.decision_engine", "Décision AAA : HOLD"),
            L(2, "INFO", "cycle_tactical", "🟡 CYCLE TACTIQUE v4.1 — démarrage"),
            L(1.9, "INFO", "agents.decision_engine", "Décision BBB : BUY"),
            "Traceback (most recent call last):\n",
            L(0.2, "INFO", "cycle_tactical", "🟡 CYCLE TACTIQUE v4.1 — démarrage"),
            L(0.1, "ERROR", SENT, "Erreur NewsAPI : 429 for url: https://x.test/v2?q=AAA&apiKey=abcdef123456")])
        ecrire(self.d.name, "tactical_errors.log", [
            L(1.8, "WARNING", SENT, "lent"), L(0.1, "ERROR", SENT, "Erreur NewsAPI : 429 apiKey=abcdef123456")])
        ecrire(self.d.name, "task_tactical.log", ["sortie brute\n"])
        ecrire(self.d.name, "alphasignal.log", [L(500, "INFO", "ancien", "journal commun")])

    def test_taches_journalisees(self):
        self.assertEqual(etat_journaux.taches_journalisees(self.d.name), ["tactical"])

    def test_passages_loggers_et_erreur(self):
        r = etat_journaux.lire_journaux(self.d.name, H(24))["tactical"]
        self.assertEqual(len(r["passages"]), 3)
        self.assertEqual(r["par_logger"]["agents.decision_engine"]["passages"], {0, 1})
        self.assertEqual(r["par_logger"]["agents.decision_engine"]["derniere"], H(1.9))
        heure, message = r["erreurs"][SENT]
        self.assertEqual(heure, H(0.1))
        self.assertIn("429", message)  # brut ici ; masqué par etat_composants avant affichage

    def test_cache_et_sauvegarde(self):
        etat_journaux.lire_journal(self.d.name, "tactical", H(24))
        with mock.patch.object(etat_journaux, "_analyser") as analyse:
            etat_journaux.lire_journal(self.d.name, "tactical", H(24))
        analyse.assert_not_called()  # fichiers inchangés : rien n'est relu
        ecrire(self.d.name, "tactical.log.1", [L(26, "INFO", "cycle_tactical", "démarrage"),
                                               L(25, "INFO", "agents.decision_engine", "x")])
        ecrire(self.d.name, "tactical.log", [L(3, "INFO", "agents.decision_engine", "y")])
        r = etat_journaux.lire_journal(self.d.name, "tactical", H(24))
        self.assertEqual(r["passages"][0], H(26))  # le fichier courant commence dans la fenêtre


SORTIE_PS = [
    {"nom": "tactical", "etat": "Ready", "dernier": "2026-10-19T07:00:01.5172934+01:00", "code": 0,
     "prochain": "2026-10-19T07:15:00.0000000+01:00",
     "declencheurs": [{"classe": "MSFT_TaskTimeTrigger", "intervalle": "PT15M"}]},
    {"nom": "weekly", "etat": "Ready", "dernier": "2026-10-18T20:00:00.0000000+01:00", "code": 0,
     "prochain": "1959-03-19T05:30:14.0000000+00:00",
     "declencheurs": [{"classe": "MSFT_TaskWeeklyTrigger", "semaines": 1}]},
    {"nom": "dashboard", "etat": "Running", "dernier": "2026-10-18T22:32:49.2741859+01:00", "code": 267009,
     "prochain": {}, "declencheurs": [{"classe": "MSFT_TaskBootTrigger"}]},
    {"nom": "daily", "etat": "Ready", "dernier": "2026-10-19T07:30:00.0000000+01:00", "code": 1,
     "declencheurs": [{"classe": "MSFT_TaskDailyTrigger", "jours": 1}]},
]


class TestTaches(unittest.TestCase):
    def setUp(self):
        etat_taches._cache.update(quand=0.0, valeur=None)

    def lire(self, **effet):
        with mock.patch.object(etat_taches.subprocess, "run", **effet) as run:
            return etat_taches.lire_taches(), run

    def test_lecture_et_normalisation(self):
        ok = subprocess.CompletedProcess([], 0, json.dumps(SORTIE_PS), "")
        t, run = self.lire(return_value=ok)
        self.assertEqual(run.call_args.kwargs["timeout"], etat_taches.DELAI_S)
        self.assertNotIn("/Run", " ".join(run.call_args.args[0]))  # lecture seule
        self.assertEqual(t["tactical"]["periode"], timedelta(minutes=15))
        self.assertEqual(t["weekly"]["periode"], timedelta(weeks=1))
        self.assertIsNone(t["weekly"]["prochain"])  # date de 1959 écartée
        self.assertIsNone(t["dashboard"]["periode"])
        self.assertFalse(t["dashboard"]["en_erreur"])  # 267009 : en cours
        self.assertTrue(t["daily"]["en_erreur"])
        with mock.patch.object(etat_taches.subprocess, "run") as run2:
            etat_taches.lire_taches()
        run2.assert_not_called()  # cache de CACHE_S secondes

    def test_echecs_inconnu(self):
        for effet in ({"side_effect": subprocess.TimeoutExpired("powershell", 6)},
                      {"side_effect": FileNotFoundError("powershell")},
                      {"return_value": subprocess.CompletedProcess([], 0, "pas du json", "")},
                      {"return_value": subprocess.CompletedProcess([], 1, "", "accès refusé")}):
            with self.subTest(effet=effet):
                etat_taches._cache.update(quand=0.0, valeur=None)
                self.assertIsNone(self.lire(**effet)[0])


class TestTables(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        self.base = os.path.join(self.d.name, "database.db")
        maintenant = datetime.now(timezone.utc)
        iso = lambda h: (maintenant - timedelta(hours=h)).isoformat(timespec="seconds")
        naif = lambda h: (maintenant - timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self.base)
        conn.execute("CREATE TABLE prices (timestamp TEXT, created_at TEXT)")
        conn.executemany("INSERT INTO prices VALUES (?, ?)", [("2020-01-01", naif(30)), ("2020-01-02", naif(1))])
        conn.execute("CREATE TABLE registre (horodatage TEXT, passage_id TEXT)")
        conn.executemany("INSERT INTO registre VALUES (?, ?)", [(iso(2), "p1"), (iso(1.5), "p1"), (iso(1), "p2")])
        conn.execute("CREATE TABLE jev_observations (horodatage TEXT, erreur TEXT)")
        conn.executemany("INSERT INTO jev_observations VALUES (?, ?)", [(iso(3), None), (iso(1), "délai dépassé")])
        conn.execute("CREATE TABLE signal_results (closed_at TEXT)")
        conn.commit()
        conn.close()

    def test_lecture(self):
        with open(self.base, "rb") as f:
            avant = hashlib.sha256(f.read()).hexdigest()
        r = etat_tables.lire_tables({"database.db": self.base, "absente.db": os.path.join(self.d.name, "x.db")},
                                    {"prices", "registre", "jev_observations", "signal_results", "inexistante"},
                                    datetime.now(timezone.utc) - timedelta(hours=24))
        self.assertEqual((r["prices"]["colonne"], r["prices"]["lignes_24h"]), ("created_at", 1))
        self.assertEqual((r["registre"]["lignes_24h"], r["registre"]["passages_24h"]), (3, 2))
        self.assertEqual(r["jev_observations"]["erreur"], "délai dépassé")
        self.assertEqual((r["signal_results"]["derniere"], r["signal_results"]["lignes_24h"]), (None, 0))
        self.assertNotIn("inexistante", r)
        with open(self.base, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), avant)  # base intacte


if __name__ == "__main__":
    unittest.main()
