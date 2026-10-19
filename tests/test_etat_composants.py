"""
tests/test_etat_composants.py — Phase 3, vue temps réel : état de chaque composant de la carte
(dashboard/api/etat_composants.py) et GET /api/topology/etat.

États déduits des sources (tâches, journaux, tables) ; secrets masqués ; une source lente, en panne
ou absente ne fait jamais échouer la réponse ; la route est en lecture seule ; la page la relit
toutes les 30 s et échappe tout ce qu'elle insère.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_etat_composants -v
Carte et sources synthétiques : sans PowerShell, sans logs/ ni base de production.
"""

import os
import re
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.api import etat_composants as ec

T0 = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
LOCAL = lambda minutes: (T0 - timedelta(minutes=minutes)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
SENT = "agents.analysts.sentiment_analyst.news_fetcher"


def noeud(cid, groupe, modules, type_="composant"):
    return {"id": cid, "libelle": cid, "groupe": groupe, "type": type_,
            "modules": [{"chemin": m, "tags": []} for m in modules]}


CARTE = {
    "groupes": [{"id": "cycles", "libelle": "Cycles"}],
    "noeuds": [noeud("cycle.tactical", "cycles", ["scripts/cycle_tactical.py"]),
               noeud("cycle.weekly", "cycles", ["scripts/cycle_weekly.py"]),
               noeud("analyst.sentiment", "analyse", ["agents/analysts/sentiment_analyst/news_fetcher.py"]),
               noeud("decision_engine", "analyse", ["agents/decision_engine.py"]),
               noeud("explorer.stock", "exploration", ["agents/explorers/stock_explorer/screener.py"]),
               noeud("registre", "execution", ["utils/registre.py"]),
               noeud("table:registre", "ressources", [], "table") | {"libelle": "registre"},
               noeud("fichier:x.md", "ressources", [], "fichier")],
    "sources_etat": {"taches": {"cycle.tactical": ["tactical"], "cycle.weekly": ["weekly"]},
                     "tables_inserees": {"registre": ["registre"]},
                     "modules_journalises": ["scripts/cycle_tactical.py", "agents/decision_engine.py",
                                             "scripts/cycle_weekly.py", "utils/registre.py"]},
}
TACHES = {"tactical": {"nom": "tactical", "etat": "Ready", "dernier": T0 - timedelta(minutes=5), "code": 0,
                       "prochain": T0 + timedelta(minutes=10), "en_erreur": False, "periode": timedelta(minutes=15)},
          "weekly": {"nom": "weekly", "etat": "Ready", "dernier": T0 - timedelta(days=20), "code": 0,
                     "prochain": None, "en_erreur": False, "periode": timedelta(weeks=1)}}
JOURNAUX = {"tactical": {
    "passages": [LOCAL(30 * 60), LOCAL(20), LOCAL(5)],
    "par_logger": {"cycle_tactical": {"derniere": LOCAL(4), "passages": {0, 1, 2}},
                   "agents.decision_engine": {"derniere": LOCAL(4), "passages": {1, 2}},
                   SENT: {"derniere": LOCAL(4), "passages": {2}}},
    "erreurs": {SENT: (LOCAL(4), "429 for url https://x.test/v2?q=AAA&apiKey=abcdef123456")},
    "premiere": LOCAL(30 * 60), "fichier": "tactical.log"}}
TABLES = {"registre": {"base": "registre.db", "colonne": "horodatage", "lignes_24h": 40, "passages_24h": 7,
                       "derniere": (T0 - timedelta(minutes=4)).isoformat(), "erreur": None}}


class BaseEtat(unittest.TestCase):
    def etat(self, taches=TACHES, journaux=JOURNAUX, tables=TABLES):
        with mock.patch.object(ec.etat_taches, "lire_taches", side_effect=lambda: taches() if callable(taches) else taches), \
                mock.patch.object(ec.etat_journaux, "lire_journaux",
                                  side_effect=lambda d, depuis: journaux() if callable(journaux) else journaux), \
                mock.patch.object(ec.etat_tables, "lire_tables",
                                  side_effect=lambda b, t, depuis: tables() if callable(tables) else tables):
            return ec.etat_des_composants(CARTE, maintenant=T0)


class TestEtats(BaseEtat):
    def test_etats_deduits(self):
        r = self.etat()
        c = r["composants"]
        self.assertEqual(r["sources"], {"taches": "ok", "journaux": "ok", "tables": "ok"})
        self.assertEqual((c["cycle.tactical"]["etat"], c["cycle.tactical"]["executions_24h"]), ("actif", 2))
        self.assertEqual(c["decision_engine"]["etat"], "actif")
        self.assertEqual(c["cycle.weekly"]["etat"], "inactif")  # 20 jours > 2 semaines
        self.assertEqual(c["analyst.sentiment"]["etat"], "en erreur")  # ERROR dans son dernier passage
        self.assertEqual(c["explorer.stock"]["etat"], "pas de source d'état")
        self.assertEqual(c["fichier:x.md"]["etat"], "pas de source d'état")
        self.assertEqual((c["registre"]["executions_24h"], c["registre"]["unite"]), (7, "passages"))
        self.assertEqual(c["table:registre"]["executions_24h"], 40)

    def test_secret_masque(self):
        erreur = self.etat()["composants"]["analyst.sentiment"]["erreur"]
        self.assertIn("apiKey=***", erreur)
        self.assertNotIn("abcdef123456", str(self.etat()))

    def test_taches_illisibles_inconnu(self):
        c = self.etat(taches=None)["composants"]
        self.assertTrue(any("inconnu" in d for d in c["cycle.tactical"]["details"]))
        self.assertEqual(c["cycle.tactical"]["etat"], "actif")  # les journaux suffisent
        sans_journaux = self.etat(taches=None, journaux={})["composants"]
        self.assertEqual(sans_journaux["cycle.weekly"]["etat"], "inconnu")

    def test_tache_en_cours_ou_en_echec(self):
        en_cours = {**TACHES, "weekly": {**TACHES["weekly"], "etat": "Running"}}
        self.assertEqual(self.etat(taches=en_cours)["composants"]["cycle.weekly"]["etat"], "actif")
        echec = {**TACHES, "tactical": {**TACHES["tactical"], "code": 1, "en_erreur": True}}
        self.assertEqual(self.etat(taches=echec)["composants"]["cycle.tactical"]["etat"], "en erreur")

    def test_source_en_panne_ou_lente(self):
        def panne():
            raise OSError("disque")
        lent = lambda: time.sleep(3) or {}
        with mock.patch.dict(ec.BUDGETS_S, {"journaux": 0.2}):
            t = time.monotonic()
            r = self.etat(journaux=lent, tables=panne)
            self.assertLess(time.monotonic() - t, 2.0)
        self.assertEqual(r["sources"], {"taches": "ok", "journaux": "indisponible", "tables": "indisponible"})
        self.assertEqual(r["composants"]["cycle.tactical"]["etat"], "actif")  # la tâche suffit
        self.assertEqual(r["composants"]["registre"]["etat"], "inconnu")


class TestRoute(BaseEtat):
    def setUp(self):
        from flask import Flask
        from dashboard.api import topology_routes
        self.routes = topology_routes
        app = Flask(__name__)
        app.register_blueprint(topology_routes.topology_api)
        self.client = app.test_client()

    def get(self):
        with mock.patch.object(self.routes, "GRAPHE", os.path.abspath(__file__)), \
                mock.patch.object(self.routes, "carte_en_cache", return_value=CARTE), \
                mock.patch.object(ec.etat_taches, "lire_taches", return_value=None), \
                mock.patch.object(ec.etat_journaux, "lire_journaux", side_effect=RuntimeError("x")), \
                mock.patch.object(ec.etat_tables, "lire_tables", return_value={}):
            return self.client.get("/api/topology/etat")

    def test_get_meme_sources_en_panne(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertIn("cycle.tactical", r.get_json()["composants"])

    def test_lecture_seule_et_sans_graphe(self):
        self.assertEqual(self.client.post("/api/topology/etat").status_code, 405)
        with mock.patch.object(self.routes, "GRAPHE", os.path.join(RACINE, "absent.json")):
            self.assertEqual(self.client.get("/api/topology/etat").status_code, 503)


class TestPage(unittest.TestCase):
    def lire(self, chemin):
        with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
            return f.read()

    def test_page_branchee(self):
        page = self.lire("dashboard/templates/architecture.html")
        js = self.lire("dashboard/static/js/architecture_etat.js")
        self.assertIn("/static/js/architecture_etat.js", page)
        self.assertIn('id="arch-etat-liste"', page)
        self.assertIn("PERIODE_MS = 30000", js)
        self.assertIn("/api/topology/etat", js)
        self.assertNotIn("method:", js)  # GET seulement
        # Dans du HTML, chaque ${…} est échappé, ou une couleur de la table ETATS, ou du HTML déjà échappé
        sures = ("escHtml(", "ETATS[", "pastille(")
        for ligne in (l for l in js.splitlines() if re.search(r"</?[a-z]", l)):  # lignes avec balises
            for expression in re.findall(r"\$\{([^}]*)\}", ligne):
                self.assertTrue(expression.startswith(sures), f"non échappé : {expression}")


if __name__ == "__main__":
    unittest.main()
