"""
tests/test_real_devise.py — D1 : devise des montants du portefeuille réel (utils/real_devise.py,
utils/real_vue.py) et libellés dans la devise de la position (« $ ») : textes et prompt LLM du
conseiller, note de calibration, messages des plans (gabarits : test_real_devise_gabarits.py).
Le capital et les budgets des plans restent en « € » ; les chiffres qui mélangent les deux sont
marqués « non converti ». Les fonctions qui alimentent le prompt du chat ne changent pas.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_real_devise -v
Base temporaire, prix simulés, valeurs inventées (règle 9) ; logs redirigés hors de logs/.
"""

import os
import re
import shutil
import sqlite3
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

from agents import plan_advisor, real_advisor
from agents.real_advisor_rules import regles_position
from scripts import migrer_devise_reelle as migration
from utils import database, real_price, real_vue
from utils import real_portfolio_db as db
from utils.real_devise import DEVISE_DEFAUT, devise_commune, devise_de, symbole

PLANS = [None,
         {"plan_type": "long_terme", "name": "Plan inventé", "objective": "objectif inventé", "vision": ""},
         {"plan_type": "court_terme", "name": "Plan court", "objective": "", "vision": ""}]
PNL_PCT = (-20.0, -10.0, 0.0, 10.0, 40.0)  # une valeur par branche des règles


def tearDownModule():
    _JOURNAUX.__exit__(None, None, None)
    shutil.rmtree(_LOGS, ignore_errors=True)


def position(**kw) -> dict:
    p = {"id": 1, "asset": "AAA", "direction": "LONG", "status": "OPEN", "entry_price": 50.0,
         "quantity": 2.5, "invested_amount": 125.0, "target_price": None, "stop_loss_mental": None,
         "investment_thesis": None, "plan_id": None}
    p.update(kw)
    return p


def textes(inv: dict, prix: float = 52.0) -> list[str]:
    out = []
    for plan in PLANS:
        for pct in PNL_PCT:
            inv_e = {"prix_actuel": prix, "pnl_pct": pct, "pnl_eur": pct * 1.25}
            out += [c["reasoning"] for c in regles_position(inv, inv_e, plan)]
    return out


class TestDevise(unittest.TestCase):
    def test_defaut_usd_tant_que_la_colonne_manque(self):
        self.assertEqual(DEVISE_DEFAUT, "USD")
        self.assertEqual(devise_de(position()), "USD")
        self.assertEqual(devise_de(position(devise=None)), "USD")
        self.assertEqual(devise_de(position(devise="eur")), "EUR")

    def test_symboles(self):
        self.assertEqual([symbole("USD"), symbole("EUR"), symbole(None), symbole("GBP")], ["$", "€", "$", "GBP"])

    def test_devise_commune(self):
        self.assertEqual(devise_commune([]), "USD")
        self.assertEqual(devise_commune([position(), position(devise="USD")]), "USD")
        self.assertIsNone(devise_commune([position(), position(devise="EUR")]))


class TestConseiller(unittest.TestCase):
    def test_textes_en_dollars_jamais_en_euros(self):
        t = textes(position())
        self.assertTrue(t)
        self.assertFalse([x for x in t if "€" in x])
        self.assertTrue(any(re.search(r"[+-]\d+\.\d{2}\$", x) for x in t))  # montants du P&L en $

    def test_cible_et_stop_libelles_dans_la_devise(self):
        inv = position(target_price=53.0, stop_loss_mental=60.0)  # 52 ≥ 53 × 0,97 et 52 ≤ 60
        t = " ".join(c["reasoning"] for c in regles_position(inv, {"prix_actuel": 52.0, "pnl_pct": 4.0,
                                                                    "pnl_eur": 5.0}, None))
        for attendu in ("cible 53.00$", "stop mental 60.00$", "actuel 52.00$"):
            self.assertIn(attendu, t)

    def test_position_en_euros_libellee_en_euros(self):
        t = textes(position(devise="EUR"))
        self.assertFalse([x for x in t if "$" in x])
        self.assertTrue(any("€" in x for x in t))

    def test_prompt_llm_du_conseiller(self):
        envoyes = []
        with mock.patch("utils.llm.ask_llm", side_effect=lambda p, **k: envoyes.append(p) or {"text": ""}):
            real_advisor._enrichir_llm([{"recommendation": "garder", "reasoning": "texte inventé"}], position(),
                                       {"pnl_pct": 4.0, "pnl_eur": 5.0}, {"name": "Plan inventé", "plan_type": "long_terme"})
        self.assertEqual(len(envoyes), 1)
        self.assertIn("Position : AAA à +4.0% (+5.00$).", envoyes[0])
        self.assertNotIn("€", envoyes[0])

    def test_enrichir_porte_la_devise(self):
        pnl = {"current_price_display": 52.0, "current_price_raw": 52.0, "entry_price_display": 50.0,
               "pnl_percent": 4.0, "pnl_euros": 5.0, "current_value": 130.0, "calibrated": False, "source": "test"}
        for retour in (pnl, None):
            with mock.patch.object(real_advisor, "calculate_position_pnl", return_value=retour):
                self.assertEqual(real_advisor._enrichir(position())["devise"], "USD")


class TestPlans(unittest.TestCase):
    def test_taille_max_investi_en_devise_et_plafond_en_euros(self):
        with mock.patch.object(plan_advisor, "positions_du_plan", return_value=[position(invested_amount=400.0)]):
            a = plan_advisor.verifier_taille_position({"id": 1, "max_position_size": 300.0})
        self.assertEqual(len(a), 1)
        self.assertIn("AAA (400$, non converti) dépasse la taille max du plan (300€)", a[0]["message"])

    def test_progression_non_convertie(self):
        with mock.patch.object(plan_advisor, "progression_plan",
                               return_value={"progression_pct": 19.0, "avancement_objectif": 95.0}):
            a = plan_advisor.verifier_progression_objectif({"id": 1, "target_return_percent": 20})
        self.assertEqual([x["alert_type"] for x in a], ["objectif_proche"])
        self.assertIn("19.0% (non converti) vs cible 20%", a[0]["message"])


class TestBaseTemporaire(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = os.path.join(self.dossier.name, "database.db")
        self.patchs = [mock.patch.object(database, "DB_PATH", self.base),
                       mock.patch.object(real_price, "prix_actuel_brut", return_value=60.0)]
        for p in self.patchs:
            p.start()
        db.initialiser_real_db()
        self.plan = db.creer_plan({"name": "Plan inventé", "plan_type": "long_terme",
                                   "allocated_budget": 300.0, "target_return_percent": 20})
        for asset, inv in (("AAA", 100.0), ("BBB", 25.0)):
            db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                       "entry_price": 50.0, "quantity": inv / 50.0, "invested_amount": inv,
                                       "plan_id": self.plan})

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def migrer_puis_une_position_en_euros(self):
        migration.migrer(self.base, appliquer=True, dossier_sauvegarde=os.path.join(self.dossier.name, "s"))
        conn = sqlite3.connect(self.base)
        conn.execute("UPDATE real_investments SET devise = 'EUR' WHERE asset = 'BBB'")
        conn.commit()
        conn.close()

    def test_vues_avec_la_devise_des_positions(self):
        b, r = real_vue.budget_reel_vue(), real_vue.resume_portefeuille_vue()
        for vue in (b, r):
            self.assertEqual((vue["devise_positions"], vue["symbole_positions"]), ("USD", "$"))
        self.assertEqual(b["invested"], 125.0)
        self.assertEqual(r["total_invested"], 125.0)
        self.migrer_puis_une_position_en_euros()
        for vue in (real_vue.budget_reel_vue(), real_vue.resume_portefeuille_vue()):
            self.assertEqual((vue["devise_positions"], vue["symbole_positions"]), (None, real_vue.MIXTE))

    def test_progression_vue_identique_a_progression_plan(self):
        v, p = real_vue.progression_plan_vue(self.plan), db.progression_plan(self.plan)
        self.assertEqual({k: v[k] for k in p}, p)
        self.assertEqual(v["symbole_positions"], "$")
        self.assertEqual(real_vue.progression_plan_vue(999), {"error": "plan introuvable"})

    def test_fonctions_du_chat_inchangees(self):
        self.assertEqual(set(db.resume_portefeuille()), {"open_count", "total_invested", "realized_pnl"})
        self.assertNotIn("devise", db.lire_investissements()[0])

    def test_note_de_calibration_dans_la_devise(self):
        with mock.patch.object(real_price, "get_current_price", return_value={"price": 100.0, "source": "test"}):
            self.assertTrue(real_vue.calibrer_vue("AAA", 101.0)["note"].startswith("Écart de 1.00$ (+1.00%)"))
            self.assertTrue(real_vue.calibrer_vue("AAA", 101.0, "EUR")["note"].startswith("Écart de 1.00€"))


if __name__ == "__main__":
    unittest.main()
