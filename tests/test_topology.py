"""
tests/test_topology.py — Tests de la carte de l'agent (/api/topology, Phase 3).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_topology -v
Sans base ni .env. Les tests sur le vrai dépôt sont sautés si
graphify-out/graph.json n'existe pas (graphify extract . --code-only).
"""

import os
import ast
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from dashboard.api import topology_sources as ts
from dashboard.api import topology_composants as tc

GRAPHE = os.path.join(RACINE, "graphify-out", "graph.json")

CODE_EXEMPLE = '''
def lancer():
    __import__("agents.b", fromlist=["X"])

def ecrire(c):
    c.execute("INSERT INTO prices (t) VALUES (?)")
    c.execute("SELECT * FROM signals s JOIN signal_results r ON 1")
    ask_llm("q", appelant="pipeline")

if __name__ == "__main__":
    ecrire(None)
    ask_gemini("demo")
'''


class TestSources(unittest.TestCase):
    """Lecture du code sur un exemple synthétique."""

    def setUp(self):
        self.arbres = {"agents/a.py": ast.parse(CODE_EXEMPLE), "agents/b.py": ast.parse("")}

    def test_nom_pointe(self):
        self.assertEqual(ts.nom_pointe("agents/skills/__init__.py"), "agents.skills")
        self.assertEqual(ts.nom_pointe("config.py"), "config")

    def test_import_dynamique(self):
        self.assertEqual(ts.imports_dynamiques(self.arbres), [("agents/a.py", "agents/b.py", 3)])

    def test_acces_tables(self):
        acces = {(t, m, f) for _, f, t, m, _, _ in ts.acces_tables(self.arbres, tc.TABLES)}
        self.assertIn(("prices", "ecrit", "ecrire"), acces)
        self.assertIn(("signals", "lit", "ecrire"), acces)
        self.assertIn(("signal_results", "lit", "ecrire"), acces)
        self.assertNotIn(("prices", "lit", "ecrire"), acces)

    def test_appels_llm_et_main(self):
        appels = ts.appels_llm(self.arbres)
        self.assertIn(("agents/a.py", "ask_llm", "pipeline", 8, False), appels)
        self.assertIn(("agents/a.py", "ask_gemini", None, 12, True), appels)
        self.assertEqual(ts.appels_de(self.arbres, {"ecrire"})["ecrire"], [("agents/a.py", 11, True)])

    def test_reserve_gemini_lue_dans_config(self):
        self.assertIn("chat", ts.reserve_gemini_defaut(RACINE) or [])

    def test_regles(self):
        self.assertEqual(tc.composant("agents/explorers/crypto_explorer/screener.py"), "explorer.crypto")
        self.assertEqual(tc.composant("agents/skills/pipeline.py"), "pipeline_v1")
        self.assertEqual(tc.composant("agents/skills/pipeline_grouped.py"), "pipeline")
        self.assertIsNone(tc.composant("inconnu/module.py"))


@unittest.skipUnless(os.path.isfile(GRAPHE), "graphify-out/graph.json absent")
class TestCarteDuDepot(unittest.TestCase):
    """Carte construite sur le vrai dépôt."""

    @classmethod
    def setUpClass(cls):
        from dashboard.api.topology_build import construire_topologie
        cls.carte = construire_topologie(RACINE, GRAPHE)
        cls.ids = {n["id"] for n in cls.carte["noeuds"]}
        cls.liens = {(l["source"], l["cible"], l["type"]) for l in cls.carte["liens"]}
        cls.incoherences = {i["id"]: i for i in cls.carte["incoherences"]}

    def test_tous_les_modules_classes(self):
        self.assertEqual(self.carte["non_classes"], [])

    def test_liens_vers_noeuds_existants(self):
        for source, cible, _ in self.liens:
            self.assertIn(source, self.ids)
            self.assertIn(cible, self.ids)

    def test_emplacement_etat_en_direct(self):
        self.assertTrue(all(n["etat"] is None for n in self.carte["noeuds"]))
        self.assertIn("etat_source", self.carte)

    def test_tactical_lance_les_7_explorateurs(self):
        explos = {c for s, c, t in self.liens if s == "cycle.tactical" and t == "import_dynamique"}
        self.assertEqual(len([e for e in explos if e.startswith("explorer.")]), 7)

    def test_incoherences_attendues(self):
        for ident in ("explorateurs_sans_prix", "cycle_lit_queue_sans_analyse",
                      "explorateurs_plusieurs_cycles", "table_sans_ecrivain_production",
                      "modules_orphelins", "code_mort"):
            self.assertIn(ident, self.incoherences)
        self.assertIn("cycle.strategic", self.incoherences["cycle_lit_queue_sans_analyse"]["noeuds"])
        sr = self.incoherences["table_sans_ecrivain_production"]
        self.assertIn("table:signal_results", sr["noeuds"])
        self.assertIn("decision_engine", sr["noeuds"])

    def test_pipeline_va_direct_a_groq(self):
        self.assertIn(("pipeline", "llm.groq", "llm"), self.liens)
        self.assertNotIn(("pipeline", "llm.gemini", "llm"), self.liens)


@unittest.skipUnless(os.path.isfile(GRAPHE), "graphify-out/graph.json absent")
class TestRoute(unittest.TestCase):
    """GET /api/topology sur une application Flask minimale (sans config.py)."""

    def setUp(self):
        from flask import Flask
        from dashboard.api import topology_routes
        self.module = topology_routes
        app = Flask(__name__)
        app.register_blueprint(topology_routes.topology_api)
        self.client = app.test_client()

    def test_get(self):
        r = self.client.get("/api/topology")
        self.assertEqual(r.status_code, 200)
        self.assertIn("noeuds", r.get_json())

    def test_lecture_seule(self):
        self.assertEqual(self.client.post("/api/topology").status_code, 405)

    def test_sans_graphe(self):
        with mock.patch.object(self.module, "GRAPHE", os.path.join(RACINE, "absent.json")):
            r = self.client.get("/api/topology")
        self.assertEqual(r.status_code, 503)
        self.assertTrue(any("requirements-dev.txt" in a for a in r.get_json()["aide"]))


if __name__ == "__main__":
    unittest.main()
