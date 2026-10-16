"""
tests/test_plan_racine.py — TODO §36, complément : un plan sans position directe additionne les
positions de ses sous-plans pour le P&L et la progression, rapportés à son propre budget ; un prix
manquant donne « non disponible » (§35) ; « aucune position » seulement sans position nulle part.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_plan_racine -v
Base temporaire : un plan racine et deux sous-plans inventés ; prix et taux simulés (1,25) ;
valeurs inventées (règle 9), sans réseau. La page Plans est exécutée par Node (sauté sans Node).
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
from tests.test_plan_sans_position import HARNAIS
from utils import database, real_price, real_vue
from utils import real_portfolio_db as db
from utils.real_conversion import AUCUNE_POSITION, SOUS_PLANS, progression_plan_connue, progression_plan_eur

P_VALEURS = ("current_value", "pnl_latent", "pnl_total", "progression_pct", "avancement_objectif")


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.prix = {"AAA": 61.0, "BBB": 30.0, "CCC": 12.0, "DDD": 9.0}  # None : pas de prix
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(real_price, "prix_actuel_brut", side_effect=lambda a: self.prix.get(a))]
        for p in self.patchs:
            p.start()
        db.initialiser_real_db()
        db.set_budget_capital(1000.0)
        self.racine = self.plan("Racine inventée", 600.0, cible=20)
        self.a = self.plan("Sous-plan A inventé", 300.0, parent=self.racine)
        self.b = self.plan("Sous-plan B inventé", 200.0, parent=self.racine)

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def plan(self, nom, budget, parent=None, cible=None) -> int:
        return db.creer_plan({"name": nom, "plan_type": "custom", "allocated_budget": budget,
                              "parent_plan_id": parent, "target_return_percent": cible})

    def position(self, asset, entree, qty, plan_id) -> None:
        db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                   "entry_price": entree, "quantity": qty, "invested_amount": entree * qty,
                                   "plan_id": plan_id})

    def deux_sous_plans(self) -> None:
        self.position("AAA", 50.0, 2.0, self.a)  # 100 $ investis, P&L 2 × (61 − 50) = 22 $
        self.position("BBB", 25.0, 4.0, self.b)  # 100 $ investis, P&L 4 × (30 − 25) = 20 $


class TestRacine(Base):
    def test_additionne_ses_sous_plans_sur_son_budget(self):
        self.deux_sous_plans()
        p = progression_plan_connue(self.racine)
        self.assertEqual(p["sous_plans_comptes"], [self.a, self.b])
        self.assertEqual((p["invested"], p["current_value"], p["pnl_total"], p["positions_count"]), (200.0, 242.0, 42.0, 2))
        self.assertFalse(p["sans_position"])
        with faux_yfinance(1.25):
            e = progression_plan_eur(self.racine)
        # 42 $ = 33,6 € ; 33,6 / 600 € (budget de la racine) = 5,6 % ; cible 20 % : 28 % du chemin
        self.assertEqual((e["pnl_total_eur"], e["progression_pct"], e["avancement_objectif"]), (33.6, 5.6, 28.0))
        self.assertTrue(e["taux_libelle"].startswith(f"{SOUS_PLANS} ; converti en € au taux EURUSD=X 1,2500"))

    def test_sous_plans_inchanges(self):
        self.deux_sous_plans()
        with faux_yfinance(1.25):
            a = progression_plan_eur(self.a)
        self.assertEqual((a["sous_plans_comptes"], a["pnl_total"], a["invested"]), ([], 22.0, 100.0))
        self.assertFalse(a["taux_libelle"].startswith(SOUS_PLANS))

    def test_prix_manquant_non_disponible(self):
        self.deux_sous_plans()
        self.prix["BBB"] = None
        with faux_yfinance(1.25) as appels:
            e = progression_plan_eur(self.racine)
        self.assertEqual([e[c] for c in P_VALEURS + ("pnl_total_eur",)], [None] * 6)
        self.assertEqual((e["actifs_sans_prix"], e["invested"]), (["BBB"], 200.0))
        self.assertEqual(e["taux_libelle"], f"{SOUS_PLANS} ; non disponible : aucun prix pour BBB")
        self.assertEqual(appels, [])  # aucun taux demandé

    def test_position_directe_seule_comptee(self):
        self.deux_sous_plans()
        self.position("CCC", 10.0, 5.0, self.racine)  # 50 $ investis, P&L 10 $
        p = progression_plan_connue(self.racine)
        self.assertEqual((p["sous_plans_comptes"], p["invested"], p["pnl_total"]), ([], 50.0, 10.0))

    def test_aucune_position_nulle_part(self):
        with faux_yfinance(1.25) as appels:
            e = progression_plan_eur(self.racine)
        self.assertTrue(e["sans_position"])
        self.assertEqual((e["sous_plans_comptes"], e["taux_libelle"]), ([], AUCUNE_POSITION))
        self.assertEqual([e[c] for c in P_VALEURS], [None] * 5)
        self.assertEqual(appels, [])

    def test_sous_plans_a_tous_les_niveaux(self):
        a1 = self.plan("Sous-sous-plan inventé", 100.0, parent=self.a)
        self.position("DDD", 8.0, 10.0, a1)  # 80 $ investis, P&L 10 $
        self.position("BBB", 25.0, 4.0, self.b)
        self.assertEqual(progression_plan_connue(self.racine)["sous_plans_comptes"], [self.a, self.b, a1])
        self.assertEqual(progression_plan_connue(self.racine)["pnl_total"], 30.0)
        self.assertEqual(progression_plan_connue(self.a)["sous_plans_comptes"], [a1])

    def test_alerte_de_progression_sur_les_sous_plans(self):
        self.deux_sous_plans()
        db.modifier_plan(self.racine, {"target_return_percent": 7})  # 5,6 / 7 : 80 % du chemin
        with faux_yfinance(1.25):
            alertes = plan_advisor.verifier_progression_objectif(db.lire_plan(self.racine))
        self.assertEqual([a["alert_type"] for a in alertes], ["progression_avance"])
        self.assertIn(SOUS_PLANS, alertes[0]["message"])


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TestPagePlans(Base):
    def test_carte_de_la_racine(self):
        self.deux_sous_plans()
        with faux_yfinance(1.25):
            donnees = {"/api/plans": db.lire_plans(), "/api/plans/alerts": []}
            for pid in (self.racine, self.a, self.b):
                donnees[f"/api/plans/{pid}/progress"] = real_vue.progression_plan_vue(pid)
                donnees[f"/api/plans/{pid}"] = {**db.lire_plan(pid), "positions": db.positions_du_plan(pid)}
        with open(os.path.join(RACINE, "dashboard", "templates", "base.html"), encoding="utf-8") as f:
            esc = [s for s in re.findall(r"<script>(.*?)</script>", f.read(), re.S) if "function escHtml" in s][0]
        with open(os.path.join(RACINE, "dashboard", "templates", "plans.html"), encoding="utf-8") as f:
            page = re.findall(r"<script>(.*?)</script>", f.read(), re.S)[0].replace("\nloadPlans();\nloadAlerts();\n", "\n")
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "page.js")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(HARNAIS.replace("DONNEES", json.dumps(donnees, default=str))
                        .replace("ESCHTML", esc).replace("PAGE", page))
            sortie = subprocess.run(["node", chemin], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        rendu = json.loads(sortie.stdout)
        carte = [c for c in rendu["liste"].split('class="card cursor-pointer"')[1:] if "Racine inventée" in c][0]
        self.assertIn("+42.00$", carte)
        self.assertIn(SOUS_PLANS, carte)
        self.assertNotIn("aucune position", carte)
        self.assertIn("+42.00$", rendu["detail"][str(self.racine)])


if __name__ == "__main__":
    unittest.main()
