"""
tests/test_plan_sans_position.py — TODO §36 : un plan sans aucune position rattachée affiche
« aucune position », jamais un P&L de 0 ; plan_advisor n'émet aucune alerte pour lui.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_plan_sans_position -v
Base temporaire, prix et taux simulés (1,25), valeurs inventées (règle 9), sans réseau.
La page Plans est exécutée par Node (sauté sans Node) avec les réponses du vrai code.
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

from agents import plan_advisor
from tests.fx_fixtures import faux_yfinance
from utils import database, real_price, real_vue
from utils import real_portfolio_db as db
from utils.real_conversion import AUCUNE_POSITION, progression_plan_connue, progression_plan_eur

P_VALEURS = ("current_value", "pnl_latent", "pnl_total", "progression_pct", "avancement_objectif")


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(real_price, "prix_actuel_brut", side_effect={"AAA": 61.0}.get)]
        for p in self.patchs:
            p.start()
        db.initialiser_real_db()
        db.set_budget_capital(1000.0)
        self.vide = db.creer_plan({"name": "Plan vide inventé", "plan_type": "custom",
                                   "allocated_budget": 300.0, "target_return_percent": 20})

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def plan_avec_position(self, statut: str = "OPEN") -> int:
        pid = db.creer_plan({"name": "Plan inventé", "plan_type": "custom", "allocated_budget": 300.0,
                             "target_return_percent": 20})
        inv = db.ajouter_investissement({"asset": "AAA", "holding_type": "moyen", "instrument_type": "normal",
                                         "entry_price": 50.0, "quantity": 2.0, "invested_amount": 100.0,
                                         "plan_id": pid})
        if statut == "CLOSED":
            db.fermer_investissement(inv, 55.0, notes="clôture inventée")
        return pid


class TestConversion(Base):
    def test_aucune_position_ni_p_l_ni_progression(self):
        p = progression_plan_connue(self.vide)
        self.assertTrue(p["sans_position"])
        self.assertEqual([p[c] for c in P_VALEURS], [None] * 5)  # et non 0
        self.assertEqual((p["invested"], p["positions_count"], p["actifs_sans_prix"]), (0, 0, []))
        with faux_yfinance(1.25) as appels:
            e = progression_plan_eur(self.vide)
        self.assertEqual(appels, [])  # aucun taux demandé : rien à convertir
        self.assertEqual((e["pnl_total_eur"], e["taux_libelle"]), (None, AUCUNE_POSITION))
        self.assertEqual(real_price.prix_actuel_brut.call_args_list, [])
        self.assertEqual(real_vue.progression_plan_vue(self.vide)["symbole_positions"], "$")

    def test_avec_une_position_inchange(self):
        for statut in ("OPEN", "CLOSED"):  # une position close suffit : P&L réalisé connu
            with self.subTest(statut=statut):
                pid = self.plan_avec_position(statut)
                ref, p = db.progression_plan(pid), progression_plan_connue(pid)
                self.assertFalse(p["sans_position"])
                self.assertEqual({k: p[k] for k in ref}, ref)
                self.assertIsNotNone(p["pnl_total"])


class TestPlanAdvisor(Base):
    def test_aucune_alerte(self):
        plan = db.lire_plan(self.vide)
        with faux_yfinance(1.25):
            self.assertEqual(plan_advisor.verifier_progression_objectif(plan), [])
            self.assertEqual(plan_advisor.verifier_plan(plan), 0)
        self.assertEqual(db.lire_alertes_plans_actives(), [])


HARNAIS = """
const donnees = DONNEES;
const elements = {};
globalThis.document = {getElementById: id => elements[id] ??= {innerHTML: "", textContent: "",
                       classList: {add() {}, remove() {}}}};
globalThis.fetch = async url => ({json: async () => donnees[url]});
globalThis.alert = globalThis.confirm = () => true;
ESCHTML
PAGE
(async () => {
  await loadPlans();
  const cartes = {};
  for (const p of donnees["/api/plans"]) {
    await openPlan(p.id);
    cartes[p.id] = elements["modal-content"].innerHTML;
  }
  console.log(JSON.stringify({liste: elements["plans"].innerHTML, detail: cartes}));
})();
"""


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TestPagePlans(Base):
    def scripts(self, nom: str) -> list[str]:
        with open(os.path.join(RACINE, "dashboard", "templates", nom), encoding="utf-8") as f:
            return re.findall(r"<script>(.*?)</script>", f.read(), re.S)

    def test_aucune_position_affiche_au_lieu_d_un_p_l_de_0(self):
        avec = self.plan_avec_position()
        with faux_yfinance(1.25):
            donnees = {"/api/plans": db.lire_plans(), "/api/plans/alerts": []}
            for pid in (self.vide, avec):
                donnees[f"/api/plans/{pid}/progress"] = real_vue.progression_plan_vue(pid)
                donnees[f"/api/plans/{pid}"] = {**db.lire_plan(pid), "positions": db.positions_du_plan(pid)}
        esc = [s for s in self.scripts("base.html") if "function escHtml" in s][0]
        page = self.scripts("plans.html")[0].replace("\nloadPlans();\nloadAlerts();\n", "\n")
        code = (HARNAIS.replace("DONNEES", json.dumps(donnees, default=str))
                .replace("ESCHTML", esc).replace("PAGE", page))
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "page.js")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(code)
            sortie = subprocess.run(["node", chemin], capture_output=True, text=True, encoding="utf-8",
                                    timeout=60)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        rendu = json.loads(sortie.stdout)
        cartes = rendu["liste"].split('class="card cursor-pointer"')[1:]
        vide, pleine = (c for c in cartes if "Plan vide inventé" in c), (c for c in cartes if "Plan vide" not in c)
        vide, pleine = next(vide), next(pleine)
        self.assertIn('<div class="font-bold">aucune position</div>', vide)
        self.assertNotIn("+0.00", vide)
        self.assertIn("+22.00$", pleine)  # 2 × (61 − 50) $
        self.assertIn(">aucune position</span>", rendu["detail"][str(self.vide)])
        self.assertIn("Avancement : aucune position", rendu["detail"][str(self.vide)])
        self.assertNotIn("+0.00", rendu["detail"][str(self.vide)])


if __name__ == "__main__":
    unittest.main()
