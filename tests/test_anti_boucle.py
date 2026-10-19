"""
tests/test_anti_boucle.py — Garde-fou anti-boucle de 24 h (REGISTRE_CRITERES v1.8, §9.4).

1. Ouverture au tactical, fermeture automatique (stop), puis tactical suivant : aucune réouverture,
   refus « anti_boucle », aucun prix frais demandé ;
2. après 24 h, ou après une fermeture qui n'est ni un stop ni un objectif (signal inverse) : réouverture
   permise ;
3. fermeture_auto_recente : stop, objectif et trailing stop bloquent pendant 24 h.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_anti_boucle -v
Base temporaire, cours inventés ; aucun réseau, aucun LLM, aucun email.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import database
from agents.paper_trader import anti_boucle, cycle, executor
from scripts import cycle_tactical
from tests.paper_fixtures import BasePaper, decision, inserer_position


class TestTacticalSuivant(BasePaper):
    def tactical(self, frais=(120.0, 30.0)):
        """Un passage du tactical sur AAA (analyse et décision simulées) ; rend (ouvertures, exécution)."""
        d, vu = decision(), {}
        espion = mock.Mock(return_value=frais)
        with mock.patch("agents.asset_analyzer.analyser_actif_complet", return_value=d["analyses"]), \
                mock.patch("agents.decision_engine.decider", return_value=d["decision"]), \
                mock.patch.object(cycle, "prix_frais", espion), \
                mock.patch.object(cycle_tactical, "enregistrer_decisions",
                                  side_effect=lambda p, dec, res, src: vu.update(res=res)):
            _, ouvertures = cycle_tactical._analyser_et_trader(["AAA"], "watchlist")
        return ouvertures, vu.get("res"), espion

    def fermer(self, statut="CLOSED_SL", il_y_a=timedelta(0)):
        p, = [x for x in self.positions() if x["status"] == "OPEN"]
        executor.fermer_position(p["id"], p["entry_price"] * 0.97, "fermeture simulée", statut)
        conn = database.get_connection()
        conn.execute("UPDATE positions SET exit_date = ? WHERE id = ?",
                     ((datetime.now(timezone.utc) - il_y_a).isoformat(timespec="seconds"), p["id"]))
        conn.commit()
        conn.close()

    def test_fermeture_puis_tactical_suivant_aucune_reouverture(self):
        self.assertEqual(self.tactical()[0], 1)
        self.fermer("CLOSED_SL")
        ouvertures, res, espion = self.tactical()
        self.assertEqual(ouvertures, 0)
        self.assertIn({"ticker": "AAA", "raisons": ["anti_boucle"]}, res["refusees"])
        espion.assert_not_called()  # bloqué avant le Budget Manager et le prix frais
        self.assertEqual(len(self.positions()), 1)

    def test_apres_24_h_reouverture_permise(self):
        self.tactical()
        self.fermer("CLOSED_TP", il_y_a=timedelta(hours=25))
        self.assertEqual(self.tactical()[0], 1)

    def test_signal_inverse_ne_bloque_pas(self):
        self.tactical()
        self.fermer("CLOSED_REVERSAL")
        self.assertEqual(self.tactical()[0], 1)


class TestFermetureAutoRecente(BasePaper):
    def test_statuts_et_delai(self):
        maintenant = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        self.assertIsNone(anti_boucle.fermeture_auto_recente("AAA", maintenant))
        for statut, ticker in (("CLOSED_SL", "AAA"), ("CLOSED_TP", "BBB"), ("CLOSED_TRAILING", "CCC")):
            inserer_position(ticker, 10.0, statut, sortie="2026-10-20T08:00:00+00:00")
            self.assertIsNotNone(anti_boucle.fermeture_auto_recente(ticker, maintenant), statut)
            self.assertIsNone(anti_boucle.fermeture_auto_recente(ticker, maintenant + timedelta(hours=21)))
        inserer_position("DDD", 10.0, "CLOSED_MANUAL", sortie="2026-10-20T08:00:00+00:00")
        self.assertIsNone(anti_boucle.fermeture_auto_recente("DDD", maintenant))


if __name__ == "__main__":
    unittest.main()
