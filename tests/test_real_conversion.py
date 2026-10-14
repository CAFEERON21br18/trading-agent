"""
tests/test_real_conversion.py — D1 : conversion en € aux points de rencontre du portefeuille réel
(utils/real_conversion.py, utils/real_vue.py, agents/plan_advisor.py). Capital et budgets des plans
en €, positions en $ : disponible, % investi, progression d'un plan (P&L converti avant la
division) et taille max sont calculés en €, le taux affiché à côté. Sans taux : « non disponible ».
Les montants des positions ne sont jamais convertis ; le P&L en % reste identique.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_real_conversion -v
Base temporaire, yfinance simulé (taux inventé 1,25), valeurs inventées (règle 9) ; logs hors de logs/.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from scripts._banc_fichiers import journaux_detaches
_LOGS = tempfile.mkdtemp()
_JOURNAUX = journaux_detaches(_LOGS)
_JOURNAUX.__enter__()  # tout le module : aucun message dans logs/ (production)

from agents import plan_advisor
from tests.fx_fixtures import faux_yfinance
from utils import database, real_price, real_vue
from utils import real_portfolio_db as db
from utils.real_conversion import investi_en_eur, progression_plan_eur, texte_taux

MONTANTS = ("plan_id", "invested", "current_value", "pnl_realise", "pnl_latent", "pnl_total",
            "target_pct", "positions_count")  # jamais convertis
PANNE = OSError("réseau coupé")


def tearDownModule():
    _JOURNAUX.__exit__(None, None, None)
    shutil.rmtree(_LOGS, ignore_errors=True)


def position(**kw) -> dict:
    p = {"id": 1, "asset": "AAA", "direction": "LONG", "status": "OPEN", "entry_price": 50.0,
         "quantity": 7.0, "invested_amount": 350.0, "plan_id": 1}
    p.update(kw)
    return p


class BaseTemporaire(unittest.TestCase):
    PRIX = {"AAA": 69.0}

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(real_price, "prix_actuel_brut", side_effect=self.PRIX.get)]
        for p in self.patchs:
            p.start()
        db.initialiser_real_db()
        db.set_budget_capital(1000.0)

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def ajouter(self, invested: float, plan_id=None, asset="AAA"):
        db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                   "entry_price": 50.0, "quantity": invested / 50.0,
                                   "invested_amount": invested, "plan_id": plan_id})


class TestBudget(BaseTemporaire):
    def test_capital_1000_eur_investi_125_usd(self):
        self.ajouter(125.0)
        with faux_yfinance(1.25):
            b, brut = real_vue.budget_reel_vue(), db.get_real_budget_summary()
        self.assertEqual((b["invested_eur"], b["available"], b["invested_percent"]), (100.0, 900.0, 10.0))
        self.assertTrue(b["taux_libelle"].startswith("converti en € au taux EURUSD=X 1,2500 ("))
        self.assertEqual(b["taux_change"]["USD"]["source"], "EURUSD=X")
        for cle in ("total_capital", "invested", "current_value", "unrealized_pnl", "unrealized_pnl_percent",
                    "by_holding", "by_instrument"):
            self.assertEqual(b[cle], brut[cle], cle)  # montants des positions : en $, inchangés
        self.assertEqual(b["invested"], 125.0)

    def test_sans_taux_non_disponible(self):
        self.ajouter(125.0)
        with faux_yfinance(erreur=PANNE):
            b = real_vue.budget_reel_vue()
        self.assertEqual((b["invested_eur"], b["available"], b["invested_percent"]), (None, None, None))
        self.assertEqual(b["taux_libelle"], "conversion en € non disponible (taux de change introuvable)")
        self.assertEqual(b["invested"], 125.0)

    def test_investi_en_eur_par_devise(self):
        positions = [position(invested_amount=125.0), position(invested_amount=40.0, devise="EUR")]
        with faux_yfinance(1.25) as appels:
            total, taux = investi_en_eur(positions)
        self.assertEqual((total, sorted(taux), appels), (140.0, ["EUR", "USD"], ["EURUSD=X"]))
        self.assertTrue(texte_taux(taux).startswith("converti en € au taux EURUSD=X 1,2500"))
        self.assertEqual(texte_taux({"EUR": taux["EUR"]}), "aucune conversion nécessaire")


class TestProgression(BaseTemporaire):
    def setUp(self):
        super().setUp()
        # budget 1200 €, cible 20 % ; 12 actions à 50 $ valant 69 $ → P&L 228 $
        self.pid = db.creer_plan({"name": "Plan inventé", "plan_type": "long_terme",
                                  "allocated_budget": 1200.0, "target_return_percent": 20})
        self.ajouter(600.0, self.pid)

    def test_95_pct_en_dollars_76_pct_en_euros(self):
        avant = db.progression_plan(self.pid)
        self.assertEqual((avant["pnl_total"], avant["avancement_objectif"]), (228.0, 95.0))
        with faux_yfinance(1.25):
            apres = progression_plan_eur(self.pid)
            alertes = plan_advisor.verifier_progression_objectif(db.lire_plan(self.pid))
        self.assertEqual((apres["pnl_total_eur"], apres["progression_pct"], apres["avancement_objectif"]),
                         (182.4, 15.2, 76.0))  # P&L converti AVANT la division par le budget
        self.assertLess(apres["avancement_objectif"], 90)
        self.assertEqual({k: apres[k] for k in MONTANTS}, {k: avant[k] for k in MONTANTS})
        # 95 % (non converti) aurait donné objectif_proche ; 76 % en € donne progression_avance
        self.assertEqual([a["alert_type"] for a in alertes], ["progression_avance"])
        self.assertIn("15.2% vs cible 20% (converti en € au taux EURUSD=X 1,2500", alertes[0]["message"])

    def test_sans_taux_ni_progression_ni_alerte(self):
        with faux_yfinance(erreur=PANNE):
            apres = progression_plan_eur(self.pid)
            alertes = plan_advisor.verifier_progression_objectif(db.lire_plan(self.pid))
        self.assertEqual((apres["progression_pct"], apres["avancement_objectif"]), (None, None))
        self.assertEqual(alertes, [])
        self.assertEqual(apres["pnl_total"], 228.0)

    def test_vue_du_dashboard(self):
        with faux_yfinance(1.25):
            v = real_vue.progression_plan_vue(self.pid)
        self.assertEqual((v["symbole_positions"], v["progression_pct"]), ("$", 15.2))
        self.assertEqual(real_vue.progression_plan_vue(999), {"error": "plan introuvable"})

    def test_sans_budget_en_euros_rapport_inchange(self):
        pid = db.creer_plan({"name": "Plan sans budget", "plan_type": "custom", "target_return_percent": 20})
        self.ajouter(500.0, pid)
        with faux_yfinance(erreur=PANNE):  # aucun taux n'est demandé
            apres = progression_plan_eur(pid)
        self.assertEqual(apres["progression_pct"], db.progression_plan(pid)["progression_pct"])
        self.assertEqual(apres["taux_libelle"], "sans conversion : budget = montant investi")


class TestTailleMax(unittest.TestCase):
    PLAN = {"id": 1, "max_position_size": 300.0}  # plafond 300 € (+5 % de tolérance : 315 €)

    def alertes(self, positions, **faux):
        with mock.patch.object(plan_advisor, "positions_du_plan", return_value=positions), faux_yfinance(**faux):
            return plan_advisor.verifier_taille_position(self.PLAN)

    def test_350_usd_pas_d_alerte(self):
        self.assertGreater(350.0, 300.0 * 1.05)  # sans conversion, 350 aurait déclenché l'alerte
        self.assertEqual(self.alertes([position(invested_amount=350.0)], taux=1.25), [])  # 280 €

    def test_400_usd_alerte(self):
        a = self.alertes([position(invested_amount=400.0)], taux=1.25)  # 320 € > 315 €
        self.assertEqual([x["alert_type"] for x in a], ["taille_position"])
        self.assertIn("AAA (400$ ≈ 320€ au taux EURUSD=X 1,2500 (", a[0]["message"])
        self.assertIn("dépasse la taille max du plan (300€)", a[0]["message"])

    def test_sans_taux_pas_de_comparaison(self):
        self.assertEqual(self.alertes([position(invested_amount=400.0)], erreur=PANNE), [])

    def test_position_en_euros_sans_conversion(self):
        a = self.alertes([position(invested_amount=320.0, devise="EUR")], erreur=PANNE)
        self.assertEqual(len(a), 1)
        self.assertIn("AAA (320€) dépasse", a[0]["message"])


if __name__ == "__main__":
    unittest.main()
