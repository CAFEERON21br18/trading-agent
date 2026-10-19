"""
tests/test_surveiller_dashboard.py — TODO §34 : surveillance du dashboard. 2 échecs consécutifs =
incident : UN email, puis un email de retour à la normale ; rien n'écoute → relance de la tâche (au plus
une fois par 15 min) ; le port écoute sans répondre → alerte seulement. /api/health : lecture seule,
sans en-tête, immédiat. installer_surveillance.ps1 : syntaxe valide, ne lance pas la tâche.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_surveiller_dashboard -v
Réseau, email et schtasks simulés ; le contrôle du port utilise un socket local (127.0.0.1) éphémère.
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from scripts import surveiller_dashboard as sd

T0 = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)


class BaseSurveillance(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.reponses, self.ecoute, self.emails, self.relances = [], True, [], []
        self.taches = {"dashboard": {"etat": "Ready", "dernier": T0 - timedelta(days=1)}}  # Get-ScheduledTaskInfo simulé
        self.patchs = [
            mock.patch.object(sd, "ETAT", os.path.join(self.dossier.name, "surveillance_dashboard.json")),
            mock.patch.object(sd, "sonder", side_effect=lambda url=sd.URL: self.reponses.pop(0)),
            mock.patch.object(sd, "port_ecoute", side_effect=lambda *a: self.ecoute),
            mock.patch.object(sd, "relancer", side_effect=lambda: self.relances.append(1) or (True, "relancée")),
            mock.patch.object(sd, "envoyer", side_effect=lambda s, c: self.emails.append((s, c)) or True),
            mock.patch("dashboard.api.etat_taches.lire_taches", side_effect=lambda: self.taches)]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def passages(self, *resultats, debut=T0, pas_min=5):
        """Un passage par résultat (True : répond), état gardé dans le fichier comme en production."""
        self.reponses += [(r, "HTTP 200" if r else "TimeoutError : délai dépassé") for r in resultats]
        for i, _ in enumerate(resultats):
            sd.ecrire_etat(sd.passage(sd.lire_etat(), debut + timedelta(minutes=pas_min * i)))
        return sd.lire_etat()


class TestIncident(BaseSurveillance):
    def test_sain_rien(self):
        etat = self.passages(True, True)
        self.assertEqual((etat["echecs"], etat["incident"], self.emails, self.relances), (0, False, [], []))

    def test_un_echec_isole_rien(self):
        etat = self.passages(False, True)
        self.assertEqual((self.emails, self.relances, etat["incident"]), ([], [], False))

    def test_port_ecoute_sans_repondre_alerte_seulement(self):
        etat = self.passages(False, False, False, False)
        self.assertEqual(len(self.emails), 1)  # UN email par incident
        self.assertIn("injoignable", self.emails[0][0])
        self.assertIn("alerte seulement", self.emails[0][1])
        self.assertEqual(self.relances, [])
        self.assertTrue(etat["incident"])

    def test_rien_n_ecoute_relance_au_plus_toutes_les_15_min(self):
        self.ecoute = False
        self.passages(False, False, False, False)  # 22h00 … 22h15 : relance à 22h05 seulement
        self.assertEqual((len(self.relances), len(self.emails)), (1, 1))
        self.assertIn(r"relance de la tâche \AlphaSignal\dashboard", self.emails[0][1])
        self.passages(False, debut=T0 + timedelta(minutes=21))  # 16 min après la relance
        self.assertEqual((len(self.relances), len(self.emails)), (2, 1))

    def test_retour_a_la_normale_un_email(self):
        self.passages(False, False, True, True)
        self.assertEqual([s for s, _ in self.emails], ["🚨 [AlphaSignal] Dashboard injoignable",
                                                        "✅ [AlphaSignal] Dashboard de nouveau joignable"])
        self.passages(False, False)  # nouvel incident : nouvel email
        self.assertEqual(len(self.emails), 3)

    def test_email_en_echec_retente_au_passage_suivant(self):
        with mock.patch.object(sd, "envoyer", side_effect=[False, True]) as envoi:
            etat = self.passages(False, False, False)
        self.assertEqual((envoi.call_count, etat["email_incident"]), (2, True))

    def test_main_ne_leve_jamais(self):
        with mock.patch.object(sd, "passage", side_effect=RuntimeError("panne simulée")):
            self.assertEqual(sd.main(), 0)


class TestFonctionsReelles(unittest.TestCase):
    def test_port_ecoute_socket_local(self):
        serveur = socket.socket()
        serveur.bind(("127.0.0.1", 0))
        serveur.listen(1)
        port = serveur.getsockname()[1]
        try:
            self.assertTrue(sd.port_ecoute("127.0.0.1", port))
        finally:
            serveur.close()
        self.assertFalse(sd.port_ecoute("127.0.0.1", port))

    def test_sonder_echec_et_relance_simules(self):
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=TimeoutError("délai dépassé")):
            self.assertEqual(sd.sonder("http://127.0.0.1:1/api/health")[0], False)
        with mock.patch.object(sd.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "SUCCESS", "")) as run:
            self.assertEqual(sd.relancer(), (True, "SUCCESS"))
        self.assertEqual(run.call_args.args[0], ["schtasks", "/Run", "/TN", r"\AlphaSignal\dashboard"])

    def test_api_health_lecture_seule_sans_en_tete(self):
        from dashboard.app import app
        from utils import heartbeat
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "heartbeat.json")
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump({"daily": {"status": "healthy", "last_run": T0.isoformat()}}, f)
            with open(chemin, "rb") as f:
                avant = hashlib.sha256(f.read()).hexdigest()
            with mock.patch.object(heartbeat, "CHEMIN_HEARTBEAT", chemin):
                t0 = time.monotonic()
                r = app.test_client().get("/api/health")
                duree = time.monotonic() - t0
            with open(chemin, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), avant)
        self.assertEqual(r.status_code, 200)
        self.assertLess(duree, 2.0)

    @unittest.skipUnless(shutil.which("powershell"), "PowerShell absent")
    def test_installeur_syntaxe_valide_sans_lancement(self):
        chemin = os.path.join(RACINE, "scripts", "installer_surveillance.ps1")
        commande = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                    f"'{chemin}', [ref]$null, [ref]$e); $e.Count")
        sortie = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", commande],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(sortie.stdout.strip(), "0", sortie.stderr)
        with open(chemin, encoding="ascii") as f:
            texte = f.read()
        self.assertIn('-TaskName "surveillance"', texte)
        self.assertIn("-RepetitionInterval (New-TimeSpan -Minutes 5)", texte)
        self.assertNotIn("Start-ScheduledTask", texte)


if __name__ == "__main__":
    unittest.main()
