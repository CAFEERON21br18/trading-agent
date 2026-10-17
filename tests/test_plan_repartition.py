"""
tests/test_plan_repartition.py — TODO §31 et §30 : plan_advisor lit la structure réelle des plans
(rules["repartition"] du plan global, clés = plan_type des sous-plans) ; « sous_repartition » n'est pas
contrôlée ; structure ambiguë → aucune alerte ; une alerte active n'est pas réinsérée ; aucun email ;
le bouton de la page Plans fonctionne toujours.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_plan_repartition -v
Base temporaire ; plans construits d'après la structure de scripts/seed_plans.py avec des noms et des
montants inventés (règle 9) ; prix et taux simulés, sans réseau.
"""

import json
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

from agents import plan_advisor
from agents.plan_repartition import verifier_repartition
from dashboard.app import app
from tests.fx_fixtures import faux_yfinance
from utils import database, real_price
from utils import real_portfolio_db as db

CIBLE = dict(type_a=40, type_b=35, type_c=25)  # types et pourcentages inventés, même structure


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch("alerts.channels.email_channel.envoyer_email"),
                       mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(real_price, "prix_actuel_brut", return_value=None),  # aucun prix
                       mock.patch.object(plan_advisor, "prix_actuel", return_value=None),  # nom importé
                       mock.patch("socket.socket.connect", side_effect=OSError("réseau coupé (test)"))]
        self.courriel = [p.start() for p in self.patchs][0]
        db.initialiser_real_db()
        conn = database.get_connection()  # colonne de la migration D1 (scripts/migrer_devise_reelle.py)
        conn.execute("ALTER TABLE real_investments ADD COLUMN devise TEXT NOT NULL DEFAULT 'USD'")
        conn.commit()
        conn.close()
        db.set_budget_capital(1000.0)
        self.racine = db.creer_plan({"name": "Racine inventée", "plan_type": "global",
                                     "allocated_budget_percent": 100, "rules": {"repartition": CIBLE}})
        self.sous = {t: db.creer_plan({"name": f"Sous-plan {t} inventé", "plan_type": t, "parent_plan_id": self.racine,
                                       "rules": {"sous_repartition": dict(categorie_a=55, categorie_b=45)}})
                     for t in CIBLE}

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def position(self, plan_id, montant, devise="USD", asset="AAA"):
        pid = db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                         "entry_price": 10.0, "quantity": montant / 10.0,
                                         "invested_amount": montant, "plan_id": plan_id})
        conn = database.get_connection()
        conn.execute("UPDATE real_investments SET devise = ? WHERE id = ?", (devise, pid))
        conn.commit()
        conn.close()

    def alertes(self):
        return verifier_repartition(db.lire_plan(self.racine), db.lire_plans())


class TestRepartition(Base):
    def test_dans_la_cible_aucune_alerte(self):
        for t, m in (("type_a", 220.0), ("type_b", 160.0), ("type_c", 120.0)):  # 44/32/24
            self.position(self.sous[t], m)
        self.assertEqual(self.alertes(), [])

    def test_hors_cible_une_seule_alerte_qui_liste_les_ecarts(self):
        for t, m in (("type_a", 400.0), ("type_b", 50.0), ("type_c", 50.0)):  # 80/10/10
            self.position(self.sous[t], m)
        alertes = self.alertes()
        self.assertEqual(len(alertes), 1)
        m = alertes[0]["message"]
        self.assertIn("type_a 80 % réel vs 40 % cible (+40 points)", m)
        self.assertIn("type_b 10 % réel vs 35 % cible (-25 points)", m)
        self.assertNotIn("type_c", m)  # écart de 15 points : pas au-delà de 15
        self.assertEqual((alertes[0]["alert_type"], alertes[0]["plan_id"]), ("deviation", self.racine))

    def test_positions_des_sous_sous_plans_comptees(self):
        petit = db.creer_plan({"name": "Sous-sous-plan inventé", "plan_type": "custom",
                               "parent_plan_id": self.sous["type_c"]})
        self.position(self.sous["type_a"], 100.0)
        self.position(self.sous["type_b"], 100.0)
        self.position(petit, 300.0)  # type_c 60 % via son sous-plan
        self.assertIn("type_c 60 % réel", self.alertes()[0]["message"])

    def test_sous_repartition_non_controlee(self):
        self.position(self.sous["type_a"], 100.0, asset="AAA")
        self.assertEqual(verifier_repartition(db.lire_plan(self.sous["type_a"]), db.lire_plans()), [])

    def hors_cible(self):
        for t, m in (("type_a", 400.0), ("type_b", 50.0), ("type_c", 50.0)):
            self.position(self.sous[t], m)
        self.assertEqual(len(self.alertes()), 1)  # témoin : sans ambiguïté, l'alerte existe

    def test_ambigu_deux_sous_plans_du_meme_type(self):
        self.hors_cible()
        db.creer_plan({"name": "Doublon inventé", "plan_type": "type_a", "parent_plan_id": self.racine})
        self.assertEqual(self.alertes(), [])

    def test_ambigu_position_sur_le_plan_lui_meme(self):
        self.hors_cible()
        self.position(self.racine, 10.0)
        self.assertEqual(self.alertes(), [])

    def test_ambigu_sous_plan_hors_repartition_avec_positions(self):
        self.hors_cible()
        self.position(db.creer_plan({"name": "Hors répartition inventé", "plan_type": "custom",
                                     "parent_plan_id": self.racine}), 10.0)
        self.assertEqual(self.alertes(), [])

    def test_ambigu_cible_qui_ne_fait_pas_100(self):
        self.hors_cible()
        db.modifier_plan(self.racine, {"rules": json.dumps({"repartition": dict(type_a=40, type_b=35)})})
        self.assertEqual(self.alertes(), [])

    def test_devises_melangees(self):
        self.position(self.sous["type_a"], 500.0, devise="USD")  # 400 € au taux 1,25
        self.position(self.sous["type_b"], 50.0, devise="EUR")
        self.position(self.sous["type_c"], 50.0, devise="EUR")
        with faux_yfinance(1.25):
            self.assertIn("type_a 80 % réel", self.alertes()[0]["message"])
        with faux_yfinance(erreur=OSError("réseau coupé")):
            self.assertEqual(self.alertes(), [])  # taux introuvable : non contrôlé


class TestAlertes(Base):
    def setUp(self):
        super().setUp()
        for t, m in (("type_a", 400.0), ("type_b", 50.0), ("type_c", 50.0)):
            self.position(self.sous[t], m)

    def test_pas_de_doublon_tant_que_active_et_aucun_email(self):
        self.assertEqual(plan_advisor.verifier_tous_les_plans(), 1)
        self.assertEqual(plan_advisor.verifier_tous_les_plans(), 0)  # alerte encore active
        actives = db.lire_alertes_plans_actives()
        self.assertEqual([(a["plan_id"], a["alert_type"]) for a in actives], [(self.racine, "deviation")])
        db.enregistrer_reponse_alerte_plan(actives[0]["id"], "suivi")
        self.assertEqual(plan_advisor.verifier_tous_les_plans(), 1)  # répondue : peut revenir
        self.courriel.assert_not_called()

    def test_bouton_de_la_page_plans(self):
        client = app.test_client()
        r = client.post("/api/plans/check-deviations", headers={"X-AlphaSignal": "1"})
        self.assertEqual((r.status_code, r.get_json()), (200, {"alertes_creees": 1}))
        self.assertEqual(client.get("/plans").status_code, 200)
        self.assertEqual(client.get("/api/plans/alerts").get_json()[0]["alert_type"], "deviation")
        self.courriel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
