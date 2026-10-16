"""
tests/test_dashboard_ecriture.py — Routes modifiantes du dashboard : en-tête X-AlphaSignal exigé.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_dashboard_ecriture -v
Client de test Flask, sans base ni réseau.
1. chaque route POST, PUT, PATCH ou DELETE (lue dans url_map) : 403 sans l'en-tête X-AlphaSignal: 1,
   vue jamais appelée ; vue atteinte avec l'en-tête ; GET inchangés ;
2. pages Plans et Réel chargées, avec le script qui ajoute l'en-tête ; chaque fetch modifiant des
   gabarits passe par base.html ;
3. ce script exécuté par Node (sauté sans Node) : en-tête sur les seuls fetch modifiants vers le dashboard.
POST et PUT /api/plans (plafond, types et bornes) : tests/test_plans_validation.py.
"""

import json
import os
import re
import shutil
import subprocess
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

from dashboard.app import app

EN_TETE = {"X-AlphaSignal": "1"}
MODIFIANTES = {"POST", "PUT", "PATCH", "DELETE"}


def routes_modifiantes() -> list[tuple[str, str, str]]:
    """(endpoint, méthode, URL construite) de chaque route modifiante de l'application."""
    adaptateur = app.url_map.bind("localhost")
    out = []
    for regle in app.url_map.iter_rules():
        for m in sorted(regle.methods & MODIFIANTES):
            out.append((regle.endpoint, m, adaptateur.build(regle.endpoint, {a: 1 for a in regle.arguments}, method=m)))
    return out


class TestEnTeteExige(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.vues = []

    def _vue(self, endpoint):
        def vue(**kw):
            self.vues.append(endpoint)
            return "atteint", 200
        return vue

    def test_chaque_route_modifiante(self):
        routes = routes_modifiantes()
        self.assertGreaterEqual(len(routes), 23)  # inventaire du 16/10/2026
        self.assertIn(("plans_api.post_plan", "POST", "/api/plans"), routes)
        for endpoint, methode, url in routes:
            with self.subTest(route=f"{methode} {url}"), \
                 mock.patch.dict(app.view_functions, {endpoint: self._vue(endpoint)}):
                for entetes in ({}, {"X-AlphaSignal": "0"}, {"Content-Type": "text/plain"}):
                    r = self.client.open(url, method=methode, headers=entetes, data="x")
                    self.assertEqual(r.status_code, 403)
                    self.assertIn("X-AlphaSignal", r.get_json()["error"])
                self.assertEqual(self.vues, [])
                r = self.client.open(url, method=methode, headers=EN_TETE)
                self.assertEqual((r.status_code, r.get_data(as_text=True)), (200, "atteint"))
                self.assertEqual(self.vues, [endpoint])
                self.vues.clear()

    def test_get_sans_en_tete_inchanges(self):
        with mock.patch.dict(app.view_functions, {"api.get_plans": self._vue("api.get_plans")}):
            self.assertEqual(self.client.get("/api/plans").status_code, 200)
        self.assertEqual(self.vues, ["api.get_plans"])


class TestPages(unittest.TestCase):
    def test_plans_et_reel_se_chargent_avec_le_script(self):
        client = app.test_client()
        for page in ("/plans", "/real"):
            with self.subTest(page=page):
                r = client.get(page)
                self.assertEqual(r.status_code, 200)
                self.assertIn('entetes.set("X-AlphaSignal", "1")', r.get_data(as_text=True))

    def test_chaque_fetch_modifiant_passe_par_base_html(self):
        """Le script de base.html couvre une page si elle en hérite ; ni formulaire POST ni XHR."""
        modifiant = re.compile(r"method:\s*[\"'](POST|PUT|PATCH|DELETE)", re.I)
        contourne = re.compile(r"<form|XMLHttpRequest|sendBeacon", re.I)
        statique = os.path.join(RACINE, "dashboard", "static")
        fichiers = [os.path.join(RACINE, "dashboard", "templates", n)
                    for n in os.listdir(os.path.join(RACINE, "dashboard", "templates"))]
        fichiers += [os.path.join(d, n) for d, _, noms in os.walk(statique) for n in noms if n.endswith(".js")]
        trouves = 0
        for chemin in fichiers:
            with open(chemin, encoding="utf-8") as f:
                texte = f.read()
            with self.subTest(fichier=os.path.basename(chemin)):
                self.assertIsNone(contourne.search(texte))
                if modifiant.search(texte):
                    trouves += 1
                    self.assertTrue(chemin.endswith(".html") and '{% extends "base.html" %}' in texte)
        self.assertEqual(trouves, 4)  # chat, plans, real, settings (16/10/2026)


HARNAIS = """
const vus = [];
globalThis.window = globalThis;
globalThis.location = new URL("http://127.0.0.1:8080/plans");
window.fetch = (cible, options) => {
  const o = options || {};
  const h = new Headers(o.headers || (cible instanceof Request ? cible.headers : undefined));
  vus.push([cible instanceof Request ? cible.url : String(cible), h.get("X-AlphaSignal"), h.get("Content-Type")]);
  return Promise.resolve(null);
};
SCRIPT
fetch("/api/plans");
fetch("/api/plans/1", {method: "PUT", headers: {"Content-Type": "application/json"}, body: "{}"});
fetch("/api/run-analysis", {method: "post"});
fetch("/api/chat/history", {method: "DELETE"});
fetch("https://exemple.invalid/api", {method: "POST"});
fetch(new Request("http://127.0.0.1:8080/api/real/calibrate", {method: "POST"}));
console.log(JSON.stringify(vus));
"""


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TestScriptDesPages(unittest.TestCase):
    def test_en_tete_sur_les_seuls_fetch_modifiants_vers_le_dashboard(self):
        with open(os.path.join(RACINE, "dashboard", "templates", "base.html"), encoding="utf-8") as f:
            script = [s for s in re.findall(r"<script>(.*?)</script>", f.read(), re.S) if "X-AlphaSignal" in s]
        self.assertEqual(len(script), 1)
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "harnais.js")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(HARNAIS.replace("SCRIPT", script[0]))
            sortie = subprocess.run(["node", chemin], capture_output=True, text=True, timeout=60)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        self.assertEqual(json.loads(sortie.stdout), [
            ["/api/plans", None, None],
            ["/api/plans/1", "1", "application/json"],
            ["/api/run-analysis", "1", None],
            ["/api/chat/history", "1", None],
            ["https://exemple.invalid/api", None, None],
            ["http://127.0.0.1:8080/api/real/calibrate", "1", None]])


if __name__ == "__main__":
    unittest.main()
