"""
tests/test_real_sans_prix.py — TODO §35 : une position réelle ouverte sans prix n'est plus comptée
comme une perte totale. Valeur, plus-value, P&L, progression et avancement passent à None
(« non disponible ») avec la liste des actifs sans prix ; investi et disponible restent donnés ;
plan_advisor n'émet aucune alerte de progression et le journalise une fois, sans montant.
Toutes les positions cotées : résultat identique à get_real_budget_summary et progression_plan.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_real_sans_prix -v
Base temporaire, prix et taux simulés (1,25), valeurs inventées (règle 9) ; logs hors de logs/.
"""

import os
import re
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

# Logs : un bloc pour les imports, puis un par test (setUp/tearDown). Pas de contexte ouvert
# jusqu'à tearDownModule : en suite complète, sa sortie rendrait le chemin de log d'un autre
# module, déjà supprimé (vu le 14/10 sur test_trade_journalist).
_LOGS = tempfile.mkdtemp()
with journaux_detaches(_LOGS):  # loggers créés à l'import : jamais vers logs/ (production)
    from agents import plan_advisor
    from tests.fx_fixtures import faux_yfinance
    from utils import database, real_price, real_vue
    from utils import real_portfolio_db as db
    from utils.real_conversion import progression_plan_connue, progression_plan_eur
shutil.rmtree(_LOGS, ignore_errors=True)

PANNE = OSError("réseau coupé")
VALEURS = ("current_value", "unrealized_pnl", "unrealized_pnl_percent")
P_VALEURS = ("current_value", "pnl_latent", "pnl_total", "progression_pct", "avancement_objectif")


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.journaux = journaux_detaches(self.dossier.name)
        self.journaux.__enter__()
        self.prix = {"AAA": 60.0, "BBB": 25.0}  # prix inventés ; None ou absent = pas de prix
        cours = lambda a: {"price": self.prix.get(a), "source": "test"}
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(real_price, "prix_actuel_brut", side_effect=lambda a: self.prix.get(a)),
                       mock.patch.object(real_price, "get_current_price", side_effect=cours)]
        for p in self.patchs:
            p.start()
        db.initialiser_real_db()
        db.set_budget_capital(1000.0)
        self.pid = db.creer_plan({"name": "Plan inventé", "plan_type": "long_terme",
                                  "allocated_budget": 400.0, "target_return_percent": 20})
        for asset, entree, qty in (("AAA", 50.0, 2.0), ("BBB", 20.0, 3.0)):  # investi 100 $ et 60 $
            db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                       "entry_price": entree, "quantity": qty, "invested_amount": entree * qty,
                                       "plan_id": self.pid})

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.journaux.__exit__(None, None, None)
        self.dossier.cleanup()


class TestToutesCotees(Base):
    def test_budget_identique_au_calcul_d_avant(self):
        with faux_yfinance(1.25):
            b = real_vue.budget_reel_vue()
        ref = db.get_real_budget_summary()
        for cle in ref:
            if cle not in ("available", "invested_percent"):  # recalculés en € depuis D1 (d4444f1)
                self.assertEqual(b[cle], ref[cle], cle)
        self.assertEqual((b["current_value"], b["unrealized_pnl"], b["actifs_sans_prix"]), (195.0, 35.0, []))

    def test_progression_identique_au_calcul_d_avant(self):
        ref = db.progression_plan(self.pid)
        p = progression_plan_connue(self.pid)
        self.assertEqual({k: p[k] for k in ref}, ref)
        self.assertEqual(p["actifs_sans_prix"], [])
        with faux_yfinance(1.25):
            e = progression_plan_eur(self.pid)
        self.assertEqual((e["pnl_total_eur"], e["progression_pct"], e["avancement_objectif"]), (28.0, 7.0, 35.0))

    def test_un_seul_prix_demande_par_actif(self):
        with faux_yfinance(1.25):
            real_vue.budget_reel_vue()
        self.assertEqual(sorted(c.args[0] for c in real_price.prix_actuel_brut.call_args_list), ["AAA", "BBB"])


class TestUnePositionSansPrix(Base):
    def setUp(self):
        super().setUp()
        self.prix["BBB"] = None

    def test_budget(self):
        with faux_yfinance(1.25):
            b = real_vue.budget_reel_vue()
        self.assertEqual([b[c] for c in VALEURS], [None, None, None])
        self.assertEqual(b["actifs_sans_prix"], ["BBB"])
        self.assertEqual(b["invested"], 160.0)  # inchangé : ne dépend pas du prix
        self.assertEqual((b["invested_eur"], b["available"], b["invested_percent"]), (128.0, 872.0, 12.8))

    def test_progression_du_plan(self):
        with faux_yfinance(1.25) as appels:
            e = progression_plan_eur(self.pid)
        self.assertEqual([e[c] for c in P_VALEURS + ("pnl_total_eur",)], [None] * 6)
        self.assertEqual(e["actifs_sans_prix"], ["BBB"])
        self.assertEqual((e["invested"], e["pnl_realise"]), (160.0, 0))
        self.assertEqual(e["taux_libelle"], "non disponible : aucun prix pour BBB")
        self.assertEqual(appels, [])  # aucun taux demandé : rien à convertir

    def test_plan_advisor_sans_alerte_un_seul_log_sans_montant(self):
        with faux_yfinance(1.25), self.assertLogs("agents.plan_advisor", level="WARNING") as journal:
            alertes = plan_advisor.verifier_progression_objectif(db.lire_plan(self.pid))
        self.assertEqual(alertes, [])
        self.assertEqual(len(journal.records), 1)
        message = journal.records[0].getMessage()
        self.assertEqual(message, "Plan « Plan inventé » : progression non disponible, 1 actif(s) sans prix")
        self.assertEqual(re.findall(r"\d+", message), ["1"])  # le nombre d'actifs, aucun montant


class TestReseauCoupe(Base):
    """Aucun prix ni taux : aucune valeur chiffrée dans les API des pages Réel et Plans."""

    def setUp(self):
        super().setUp()
        self.prix.clear()
        from flask import Flask
        from dashboard.api.routes import api
        app = Flask(__name__)
        app.register_blueprint(api)
        self.client = app.test_client()

    def test_api_reel_et_plans(self):
        with faux_yfinance(erreur=PANNE):
            b = self.client.get("/api/real/budget").get_json()
            p = self.client.get(f"/api/plans/{self.pid}/progress").get_json()
            positions = self.client.get("/api/real/investments?status=OPEN").get_json()
        self.assertEqual([b[c] for c in VALEURS + ("available", "invested_percent", "invested_eur")], [None] * 6)
        self.assertEqual((b["actifs_sans_prix"], b["invested"]), (["AAA", "BBB"], 160.0))
        self.assertEqual([p[c] for c in P_VALEURS + ("pnl_total_eur",)], [None] * 6)
        self.assertEqual(len(positions), 2)
        for x in positions:
            self.assertEqual((x["prix_actuel"], x["pnl_eur"], x["pnl_pct"]), (None, None, None))

    def test_gabarits_jamais_un_chiffre_a_la_place_de_l_inconnu(self):
        with open(os.path.join(RACINE, "dashboard", "templates", "real.html"), encoding="utf-8") as f:
            real = f.read()
        with open(os.path.join(RACINE, "dashboard", "templates", "plans.html"), encoding="utf-8") as f:
            plans = f.read()
        self.assertIn('b.current_value == null ? "non disponible"', real)
        self.assertIn('b.unrealized_pnl == null ? "non disponible"', real)
        self.assertIn("sans prix : ${escHtml(b.actifs_sans_prix", real)
        self.assertEqual(plans.count('prog.pnl_total == null ? "non disponible"'), 2)  # carte et détail
        self.assertIn('prog.current_value == null ? "non disponible"', plans)
        for t in (real, plans):  # plus de valeur inconnue remplacée par 0
            self.assertNotIn("current_value?.toFixed(2) || 0", t)
            self.assertNotIn("unrealized_pnl_percent || 0", t)


if __name__ == "__main__":
    unittest.main()
