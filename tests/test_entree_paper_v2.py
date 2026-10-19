"""
tests/test_entree_paper_v2.py — Version 2 du mécanisme d'entrée paper (REGISTRE_CRITERES v1.8, §9.4).

1. prix_frais : dernière barre de 1 minute de moins de 15 min, sinon None (vieille, vide, illisible, erreur) ;
2. executer_ouvertures : SL, TP et taille recalculés sur le prix frais ; version 2, prix de la décision,
   prix d'exécution et âge inscrits avec la position ;
3. sans prix frais : aucune ouverture, refus « prix_frais_indisponible », Risk Manager non appelé ;
4. une même décision ne change ni d'action ni de confiance : seuls le prix, le SL, le TP et la taille changent.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_entree_paper_v2 -v
Base temporaire, cours inventés ; aucun réseau, aucun LLM, aucun email.
"""

import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import pandas as pd

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import database
from agents.paper_trader import cycle, prix_frais as pf
from tests.paper_fixtures import BasePaper, decision

MAINTENANT = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)


def barres(minutes_avant: float, close: float = 120.0, nan_fin: bool = False) -> pd.DataFrame:
    fin = MAINTENANT - timedelta(minutes=minutes_avant)
    index = pd.DatetimeIndex([fin - timedelta(minutes=2), fin - timedelta(minutes=1), fin])
    closes = [close - 1, close - 0.5, float("nan") if nan_fin else close]
    return pd.DataFrame({"Close": closes}, index=index)


class TestPrixFrais(unittest.TestCase):
    def test_barre_recente_retenue(self):
        r = pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: barres(3))
        self.assertEqual(r, (120.0, 180.0))

    def test_refus_vieille_vide_illisible_erreur(self):
        self.assertIsNone(pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: barres(16)))
        self.assertIsNone(pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: pd.DataFrame({"Close": []})))
        self.assertIsNone(pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: None))
        self.assertIsNone(pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: barres(3, close=0.0)))

        def panne(t):
            raise TimeoutError("délai dépassé")
        self.assertIsNone(pf.prix_frais("AAA", MAINTENANT, telecharger=panne))

    def test_derniere_barre_sans_prix_ignoree(self):
        # la dernière barre est NaN : on prend la précédente, une minute plus tôt
        self.assertEqual(pf.prix_frais("AAA", MAINTENANT, telecharger=lambda t: barres(3, nan_fin=True)),
                         (119.5, 240.0))


class TestOuverture(BasePaper):
    def ouvrir(self, frais, d=None):
        espion = mock.Mock(wraps=cycle.valider_signal)
        with mock.patch.object(cycle, "prix_frais", return_value=frais), \
                mock.patch.object(cycle, "valider_signal", espion):
            res = cycle.executer_ouvertures([d or decision()])
        return res, espion

    def test_sl_tp_taille_sur_le_prix_frais(self):
        res, espion = self.ouvrir((120.0, 42.0))
        self.assertEqual(len(res["ouvertes"]), 1, res["refusees"])
        (args, kwargs), = [c[:2] for c in espion.call_args_list]
        self.assertEqual(args[2], 120.0)  # le Risk Manager recalcule sur le prix frais
        attendu = cycle.valider_signal("AAA", "LONG", 120.0, budget_alloue=kwargs["budget_alloue"])["signal"]
        p, = self.positions()
        for col, cle in (("entry_price", "prix_entree"), ("stop_loss", "stop_loss"), ("target_1", "target_1"),
                         ("target_2", "target_2"), ("quantity", "taille_unites"), ("invested_amount", "montant_investi")):
            self.assertAlmostEqual(p[col], attendu[cle], places=9, msg=col)
        self.assertEqual((p["mecanisme_entree"], p["prix_decision"], p["prix_execution"], p["age_prix_s"]),
                         (2, 117.0, 120.0, 42.0))

    def test_refus_sans_prix_frais(self):
        res, espion = self.ouvrir(None)
        self.assertEqual(res["ouvertes"], [])
        self.assertIn({"ticker": "AAA", "raisons": ["prix_frais_indisponible"]}, res["refusees"])
        espion.assert_not_called()
        self.assertEqual(self.positions(), [])

    def test_decision_inchangee_seuls_prix_sl_tp_taille_changent(self):
        d = decision()
        avant = copy.deepcopy(d["decision"])
        self.ouvrir((117.0, 10.0), d)
        self.assertEqual(d["decision"], avant)  # ni l'action ni la confiance ne changent
        p1, = self.positions()
        conn = database.get_connection()
        conn.execute("DELETE FROM positions")
        conn.commit()
        conn.close()
        d2 = decision()
        self.ouvrir((125.0, 10.0), d2)
        self.assertEqual(d2["decision"], avant)
        p2, = self.positions()
        changent = {"id", "entry_price", "stop_loss", "target_1", "target_2", "quantity", "invested_amount",
                    "prix_execution", "entry_date", "created_at"}
        for col in set(p1) - changent:
            self.assertEqual(p1[col], p2[col], col)
        for col in ("entry_price", "stop_loss", "target_1"):
            self.assertNotEqual(p1[col], p2[col], col)


if __name__ == "__main__":
    unittest.main()
