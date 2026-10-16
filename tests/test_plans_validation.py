"""
tests/test_plans_validation.py — POST et PUT /api/plans validés (TODO §7).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_plans_validation -v
Client de test Flask, base temporaire, valeurs inventées (règle 9), sans réseau.
- POST : plafond du mode plan du chat (agents/chat/_plan_budget.py), 400 au-delà ; un plan qui ne
  réserve rien (sous-plan d'un plan actif, plan inactif, sans budget) est accepté ;
- POST et PUT : types et bornes (400) ; la modification de la page Plans passe toujours.
"""

import os
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
from utils import database
from utils import real_portfolio_db as db

EN_TETE = {"X-AlphaSignal": "1"}


class BasePlans(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patch = mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db"))
        self.patch.start()
        db.initialiser_real_db()
        db.set_budget_capital(1000.0)  # valeurs inventées
        db.ajouter_investissement({"asset": "AAA", "holding_type": "moyen", "instrument_type": "normal",
                                   "entry_price": 50.0, "quantity": 2.0, "invested_amount": 100.0})
        self.client = app.test_client()

    def tearDown(self):
        self.patch.stop()
        self.dossier.cleanup()

    def post(self, **plan):
        return self.client.post("/api/plans", json={"name": "Plan inventé", "plan_type": "custom", **plan},
                                headers=EN_TETE)

    def put(self, plan_id, corps):
        return self.client.put(f"/api/plans/{plan_id}", json=corps, headers=EN_TETE)


class TestPlafondCreation(BasePlans):
    """Plafond du chat : capital 1000 − investi 100 − budget restant des plans actifs."""

    def test_au_dela_du_plafond_400(self):
        self.assertTrue(self.post(allocated_budget=400.0).get_json()["saved"])  # plafond 900 → 500
        r = self.post(allocated_budget=600.0)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Budget trop élevé", r.get_json()["error"])
        self.assertEqual(self.post(allocated_budget_percent=60).status_code, 400)  # 600 € > 500
        self.assertEqual(self.post(allocated_budget_percent=40).status_code, 200)  # 400 € ≤ 500
        self.assertEqual(len(db.lire_plans()), 2)

    def test_plans_qui_ne_reservent_rien_acceptes(self):
        parent = self.post(allocated_budget=900.0).get_json()["id"]  # plafond 0 ensuite
        self.assertEqual(self.post(allocated_budget=50.0).status_code, 400)
        self.assertEqual(self.post(allocated_budget=50.0, parent_plan_id=parent).status_code, 200)
        self.assertEqual(self.post(allocated_budget=50.0, status="paused").status_code, 200)
        self.assertEqual(self.post().status_code, 200)  # sans budget
        self.assertEqual(self.post(allocated_budget=50.0, parent_plan_id=999).status_code, 400)


class TestTypesEtBornes(BasePlans):
    def test_post_refuse(self):
        for corps in ({"allocated_budget": -1}, {"allocated_budget": "100"}, {"allocated_budget": True},
                      {"allocated_budget_percent": 150}, {"allocated_budget_percent": -5},
                      {"status": "inconnu"}, {"status": None}, {"target_amount": -3}, {"name": 12},
                      {"parent_plan_id": "1"}, {"target_return_percent": float("nan")}):
            with self.subTest(corps=corps):
                r = self.post(**corps)
                self.assertEqual(r.status_code, 400, r.get_json())
        r = self.client.post("/api/plans", json={"plan_type": "custom"}, headers=EN_TETE)
        self.assertEqual(r.get_json(), {"error": "name et plan_type requis"})
        self.assertEqual(self.client.post("/api/plans", json=[1], headers=EN_TETE).status_code, 400)
        self.assertEqual(db.lire_plans(), [])

    def test_put(self):
        pid = self.post(allocated_budget=100.0).get_json()["id"]
        champs = {"objective": "objectif inventé", "target_return_percent": 250.0, "target_amount": None}
        self.assertEqual(self.put(pid, champs).get_json(), {"updated": True})  # comme la page Plans
        for corps in ({"allocated_budget_percent": 101}, {"allocated_budget": -10}, {"status": "zzz"},
                      {"rules": {"a": 1}}, {"name": ""}, {"time_horizon": 5}):
            with self.subTest(corps=corps):
                self.assertEqual(self.put(pid, corps).status_code, 400)
        self.assertEqual(self.client.put(f"/api/plans/{pid}", data="x", headers=EN_TETE).status_code, 400)
        self.assertEqual(db.lire_plan(pid)["objective"], "objectif inventé")


if __name__ == "__main__":
    unittest.main()
