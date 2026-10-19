"""
tests/test_relance_dashboard.py — Relance concurrente du dashboard (19/10/2026, 13:30:41 : tâche finie en -1
juste après une relance manuelle Stop-Process puis Start-ScheduledTask).

1. La surveillance ne relance jamais une tâche déjà en cours (Running), ni démarrée il y a moins de
   3 minutes, ni si son état est illisible ; elle relance encore une tâche arrêtée depuis plus longtemps.
2. Un second dashboard qui trouve le port pris s'arrête proprement (code 0, message clair) au lieu de
   se lier lui aussi au port (SO_REUSEADDR de Werkzeug sous Windows) : socket local réel, et
   dashboard/app.py exécuté comme script avec Flask.run simulé.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_relance_dashboard -v
Sans PowerShell, sans schtasks, sans email : tout est simulé.
"""

import os
import runpy
import socket
import sys
import unittest
from datetime import timedelta
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard import demarrage
from tests.test_surveiller_dashboard import T0, BaseSurveillance, sd


class TestSurveillance(BaseSurveillance):
    def incident_port_ferme(self, taches):
        self.ecoute, self.taches = False, taches
        return self.passages(False, False)  # 2e échec à T0 + 5 min : incident, rien n'écoute

    def test_tache_en_cours_pas_de_relance(self):
        etat = self.incident_port_ferme({"dashboard": {"etat": "Running", "dernier": T0 - timedelta(hours=2)}})
        self.assertEqual(self.relances, [])
        self.assertIn("déjà en cours", etat["relance"])
        self.assertEqual(len(self.emails), 1)  # l'alerte part quand même

    def test_demarrage_recent_pas_de_relance_puis_relance(self):
        recente = {"dashboard": {"etat": "Ready", "dernier": T0 + timedelta(minutes=4)}}  # 1 min avant le 2e passage
        etat = self.incident_port_ferme(recente)
        self.assertEqual(self.relances, [])
        self.assertIn("moins de 3 minutes", etat["relance"])
        self.passages(False, debut=T0 + timedelta(minutes=10))  # 6 min après ce démarrage : relance
        self.assertEqual(self.relances, [1])

    def test_etat_illisible_pas_de_relance(self):
        for taches in (None, {}):
            with self.subTest(taches=taches):
                self.relances.clear()
                sd.ecrire_etat({})  # nouvel incident pour chaque cas
                etat = self.incident_port_ferme(taches)
                self.assertEqual(self.relances, [])
                self.assertIn("illisible", etat["relance"])

    def test_lecture_en_erreur_ne_leve_pas(self):
        with mock.patch("dashboard.api.etat_taches.lire_taches", side_effect=OSError("PowerShell absent")):
            self.ecoute = False
            etat = self.passages(False, False)
        self.assertEqual(self.relances, [])
        self.assertIn("illisible", etat["relance"])

    def test_tache_arretee_depuis_longtemps_relancee(self):
        self.incident_port_ferme({"dashboard": {"etat": "Ready", "dernier": T0 - timedelta(days=1)}})
        self.assertEqual(self.relances, [1])


class TestSecondDemarrage(unittest.TestCase):
    def setUp(self):
        self.serveur = socket.socket()
        self.serveur.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # comme Werkzeug
        self.serveur.bind(("127.0.0.1", 0))
        self.port = self.serveur.getsockname()[1]
        self.addCleanup(self.serveur.close)

    def test_port_occupe(self):
        # Lié sans écouter : la connexion échoue, mais la liaison exclusive voit le port pris
        self.assertIn("liaison impossible", demarrage.port_occupe("127.0.0.1", self.port))
        self.serveur.listen()
        self.assertIn("répond déjà", demarrage.port_occupe("127.0.0.1", self.port))

    def test_port_libre(self):
        libre = socket.socket()
        libre.bind(("127.0.0.1", 0))
        port = libre.getsockname()[1]
        libre.close()
        self.assertIsNone(demarrage.port_occupe("127.0.0.1", port))

    def lancer_app(self, port):
        with mock.patch.dict(os.environ, {"DASHBOARD_HOST": "127.0.0.1", "DASHBOARD_PORT": str(port)}), \
                mock.patch("flask.Flask.run") as run, mock.patch.object(sys, "stderr"):
            try:
                runpy.run_path(os.path.join(RACINE, "dashboard", "app.py"), run_name="__main__")
                code = None
            except SystemExit as e:
                code = e.code
        return code, run

    def test_app_s_arrete_proprement_si_le_port_est_pris(self):
        self.serveur.listen()
        with self.assertLogs("__main__", "WARNING") as journal:
            code, run = self.lancer_app(self.port)
        self.assertEqual(code, 0)
        run.assert_not_called()
        self.assertIn(f"Port {self.port} déjà utilisé", "\n".join(journal.output))

    def test_app_demarre_si_le_port_est_libre(self):
        self.serveur.close()
        code, run = self.lancer_app(self.port)
        self.assertIsNone(code)
        self.assertEqual(run.call_args.kwargs["port"], self.port)


if __name__ == "__main__":
    unittest.main()
