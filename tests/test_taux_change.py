"""
tests/test_taux_change.py — Taux EURUSD quotidien vers le grand livre (importeurs/taux_change.py).

1. Les clôtures sont inscrites dans la table change, arrondies à 6 décimales ; relancer n'ajoute
   aucun doublon et un jour déjà présent n'est pas réécrit ;
2. le jour en cours, une valeur invalide et un jour hors période sont écartés ;
3. à blanc : rien n'est écrit ; source en échec : erreur explicite, rien n'est écrit ;
4. après import, la bascule de mesures trouve le taux, week-end compris ;
5. cloture_yfinance : ticker, intervalle et bornes demandés, lecture des barres, échecs convertis
   (faux module yfinance, aucun appel réseau) ;
6. période par défaut : 365 jours sans taux stocké, sinon 7 jours avant le dernier, jusqu'à hier.
Le script est testé dans tests/test_ledger_taux.py.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_taux_change -v
Source de cours simulée, taux inventés ; base dans un dossier temporaire ; aucun réseau (toute
connexion lève une erreur), aucun .env, rien dans data/.
"""

import os
import sys
import types
import unittest
from datetime import date
from decimal import Decimal as D
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
import mesures
from importeurs import taux_change as tc
from tests.socle_fixtures import jour
from tests.socle_taux_fixtures import AUJOURD_HUI, SansReseau

class TestImporter(SansReseau):
    def test_clotures_inscrites_puis_aucun_doublon(self):
        r = self.importer()
        self.assertEqual((r.ajoutes, r.deja_presents, r.ecartes, r.premier, r.dernier),
                         (3, 0, [], date(2030, 1, 7), date(2030, 1, 9)))
        lignes = self.conn.execute("SELECT jour, paire, taux, source FROM change ORDER BY id").fetchall()
        self.assertEqual([tuple(l) for l in lignes],
                         [("2030-01-07", "EURUSD", "1.250000", "yfinance EURUSD=X"),
                          ("2030-01-08", "EURUSD", "1.251235", "yfinance EURUSD=X"),
                          ("2030-01-09", "EURUSD", "1.260000", "yfinance EURUSD=X")])
        r = self.importer([(date(2030, 1, 8), 1.99), (date(2030, 1, 9), 1.26)])  # relance, valeur différente
        self.assertEqual((r.ajoutes, r.deja_presents), (0, 2))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM change").fetchone()[0], 3)
        self.assertEqual(ledger.taux_eurusd(self.conn)[date(2030, 1, 8)], D("1.251235"))  # non réécrit

    def test_jour_en_cours_valeur_invalide_et_hors_periode_ecartes(self):
        cours = [(date(2029, 12, 31), 1.20), (date(2030, 1, 7), float("nan")), (date(2030, 1, 8), 0.0),
                 (date(2030, 1, 9), 1.26), (date(2030, 1, 9), 1.27), (AUJOURD_HUI, 1.28), (date(2030, 1, 11), None)]
        r = self.importer(cours, fin=date(2030, 1, 10))
        self.assertEqual(r.ajoutes, 1)
        self.assertEqual([j for j, _ in r.ecartes], [date(2030, 1, 7), date(2030, 1, 8), AUJOURD_HUI])
        self.assertIn("non terminée", r.ecartes[2][1])
        self.assertEqual(ledger.taux_eurusd(self.conn), {date(2030, 1, 9): D("1.27")})  # dernier cité

    def test_a_blanc_rien_n_est_ecrit(self):
        r = self.importer(appliquer=False)
        self.assertEqual(r.ajoutes, 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM change").fetchone()[0], 0)

    def test_source_en_echec_rien_n_est_ecrit(self):
        def en_panne(debut, fin):
            raise tc.SourceIndisponible("cours indisponible")
        with self.assertRaises(tc.SourceIndisponible):
            tc.importer(self.conn, date(2030, 1, 1), date(2030, 1, 9), en_panne, aujourd_hui=AUJOURD_HUI)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM change").fetchone()[0], 0)

    def test_bascule_de_mesures_apres_import(self):
        self.importer([(date(2030, 1, 4), 1.25)])  # un vendredi
        t = mesures.TradeClos(1, "AAA", "long", D("1"), D("100"), D("225"), jour(3), jour(6),
                              "USD", D("125"), D("0"), D("25"))  # clos le dimanche 6
        c = mesures.en_devise([t], "EUR", ledger.taux_eurusd(self.conn))[0]
        self.assertEqual((c.devise, c.pnl_brut, c.risque), ("EUR", D("100"), D("20")))

    def test_periode_par_defaut(self):
        self.assertEqual(tc.periode_par_defaut(self.conn, AUJOURD_HUI), (date(2029, 1, 10), date(2030, 1, 9)))
        self.importer([(date(2030, 1, 4), 1.25)])
        self.assertEqual(tc.periode_par_defaut(self.conn, AUJOURD_HUI), (date(2029, 12, 28), date(2030, 1, 9)))


class TestClotureYfinance(unittest.TestCase):
    """cloture_yfinance sur un faux module yfinance : aucun appel réseau."""

    def appeler(self, history):
        demandes = []

        class Ticker:
            def __init__(self, symbole):
                demandes.append(symbole)

            def history(self, **kw):
                demandes.append(kw)
                return history()
        faux = types.SimpleNamespace(Ticker=Ticker)
        with mock.patch.dict(sys.modules, {"yfinance": faux}), \
                mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")):
            return tc.cloture_yfinance(date(2030, 1, 7), date(2030, 1, 9)), demandes

    def test_barres_lues(self):
        import pandas as pd
        index = pd.DatetimeIndex(["2030-01-07", "2030-01-08"], tz="Europe/London")
        cours, demandes = self.appeler(lambda: pd.DataFrame({"Close": [1.25, 1.26]}, index=index))
        self.assertEqual(cours, [(date(2030, 1, 7), 1.25), (date(2030, 1, 8), 1.26)])
        self.assertEqual(demandes[0], "EURUSD=X")
        self.assertEqual((demandes[1]["start"], demandes[1]["end"], demandes[1]["interval"]),
                         ("2030-01-07", "2030-01-10", "1d"))  # borne de fin exclue par yfinance

    def test_echecs_convertis(self):
        import pandas as pd

        def en_panne():
            raise ConnectionError("réseau coupé")
        for history in (en_panne, lambda: pd.DataFrame(), lambda: None):
            with self.subTest(history=history):
                with self.assertRaises(tc.SourceIndisponible):
                    self.appeler(history)


if __name__ == "__main__":
    unittest.main()
