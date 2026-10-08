"""
tests/test_jev_fantome_sorties.py — Fantôme Jev (REGISTRE_CRITERES §8.2) : sortie à J+5
de bourse, coûts, jamais deux positions fantômes sur le même actif, rattrapage.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_fantome_sorties -v
Base SQLite temporaire, valeurs inventées, aucun réseau.
"""

import sqlite3
import unittest

from tests.jev_fantome_fixtures import BaseFantome, observation  # en premier : variables de config.py
from utils import database
from scripts import jev_bilan_calc as calc


class TestSortieJ5(BaseFantome):

    def _rendement_7_1(self, ticker: str, jour: str, p0: float) -> float:
        conn = sqlite3.connect(database.DB_PATH)
        try:
            return calc.rendement(conn, ticker, jour, p0)
        finally:
            conn.close()

    def test_action_week_end_et_thanksgiving(self):
        # Lundi 23/11/2026 ; jeudi 26/11 férié (Thanksgiving), pas de barre ; week-end 28-29/11
        self.ajouter_obs(observation("AAPL", "2026-11-23", prix=100.0))
        self.ajouter_barres("AAPL", {"2026-11-23": 101.0, "2026-11-24": 102.0, "2026-11-25": 103.0,
                                     "2026-11-27": 104.0, "2026-11-30": 105.0, "2026-12-01": 99.0})
        self.lancer("2026-11-23")
        self.lancer("2026-11-30")  # la 5e barre (30/11) n'est pas close au cycle de 7h30 du 30/11
        self.assertEqual(self.positions()[0]["statut"], "OPEN")
        self.assertEqual(self.lancer("2026-12-01")["sorties"], 1)
        p, = self.positions()
        self.assertEqual((p["statut"], p["barre_sortie"], p["jour_sortie"]), ("CLOSED", "2026-11-30", "2026-12-01"))
        self.assertEqual(p["prix_sortie"], 105.0)
        self.assertAlmostEqual(p["pnl_pct"], self._rendement_7_1("AAPL", "2026-11-23", 100.0))  # même J+5 que le §7

    def test_future_la_barre_du_jour_ferie_compte_comme_au_7_1(self):
        # Vendredi 04/09/2026 ; lundi 07/09 Labor Day : barre pour le future, pas pour l'ETF
        self.ajouter_obs(observation("GC=F", "2026-09-04"), observation("SPY", "2026-09-04"))
        self.ajouter_barres("GC=F", {f"2026-09-{j:02d}": 100.0 + j for j in (4, 7, 8, 9, 10, 11)})
        self.ajouter_barres("SPY", {f"2026-09-{j:02d}": 100.0 + j for j in (4, 8, 9, 10, 11)})
        self.lancer("2026-09-04")
        self.lancer("2026-09-14")
        barres = {p["ticker"]: p["barre_sortie"] for p in self.positions()}
        self.assertEqual(barres, {"GC=F": "2026-09-10", "SPY": "2026-09-11"})
        for p in self.positions():
            self.assertAlmostEqual(p["pnl_pct"], self._rendement_7_1(p["ticker"], "2026-09-04", 100.0))

    def test_crypto_jours_calendaires_et_barre_du_jour_non_close(self):
        self.ajouter_obs(observation("BTC-USD", "2026-09-04"))
        self.ajouter_barres("BTC-USD", {f"2026-09-{j:02d}": 100.0 + j for j in range(4, 10)})
        self.lancer("2026-09-04")
        self.lancer("2026-09-08")  # barre du 08/09 en cours à 7h30 : pas de sortie
        self.assertEqual(self.positions()[0]["statut"], "OPEN")
        self.lancer("2026-09-09")
        p, = self.positions()
        self.assertEqual((p["barre_sortie"], p["prix_sortie"]), ("2026-09-08", 108.0))

    def test_pas_de_sortie_sans_5e_barre(self):
        self.ajouter_obs(observation("SPY", "2026-11-02"))
        self.ajouter_barres("SPY", {"2026-11-02": 100.0, "2026-11-03": 100.0, "2026-11-04": 100.0})
        self.lancer("2026-11-02")
        self.lancer("2026-11-20")
        self.assertEqual(self.positions()[0]["statut"], "OPEN")

    def test_couts_aller_retour_du_7_1(self):
        self.ajouter_obs(observation("BTC-USD", "2026-09-04"), observation("SPY", "2026-09-04"))
        barres = {f"2026-09-{j:02d}": 110.0 for j in range(4, 12)}
        self.ajouter_barres("BTC-USD", barres)
        self.ajouter_barres("SPY", barres)
        self.lancer("2026-09-04")
        self.lancer("2026-09-14")
        net = {p["ticker"]: (p["cout_pct"], round(p["pnl_brut"], 6), round(p["pnl_net"], 6))
               for p in self.positions()}
        # 40 € à 100, sortie à 110 : +4 € bruts ; coût 1,0 % (crypto) ou 0,2 % du montant investi
        self.assertEqual(net, {"BTC-USD": (0.010, 4.0, 3.6), "SPY": (0.002, 4.0, 3.92)})


class TestJamaisDeuxPositions(BaseFantome):

    BARRES = {f"2026-11-{j:02d}": 100.0 for j in (2, 3, 4, 5, 6, 9, 10)}

    def test_deuxieme_observation_refusee_tant_que_la_position_est_ouverte(self):
        self.ajouter_obs(observation("SPY", "2026-11-02", p_acheter=0.8),
                         observation("SPY", "2026-11-06", p_acheter=0.95))
        self.ajouter_barres("SPY", self.BARRES)
        self.lancer("2026-11-02")
        self.lancer("2026-11-06")  # 5e barre datée du 06/11 : pas encore close
        self.assertEqual(len(self.positions()), 1)
        self.assertEqual(self.refus(), {"SPY": "position_fantome_ouverte"})

    def test_sortie_passee_avant_l_entree_du_meme_jour(self):
        self.ajouter_obs(observation("SPY", "2026-11-02"), observation("SPY", "2026-11-09", p_acheter=0.9))
        self.ajouter_barres("SPY", self.BARRES)
        self.lancer("2026-11-02")
        self.lancer("2026-11-09")
        statuts = [(p["jour_entree"], p["statut"]) for p in self.positions()]
        self.assertEqual(statuts, [("2026-11-02", "CLOSED"), ("2026-11-09", "OPEN")])

    def test_relancer_ne_cree_aucun_doublon(self):
        self.ajouter_obs(observation("SPY", "2026-11-02"))
        self.lancer("2026-11-02")
        self.assertEqual(self.lancer("2026-11-02"), {"jours": 1, "entrees": 0, "refus": 0, "sorties": 0})
        self.assertEqual((len(self.positions()), len(self.lire("jev_paper_journal"))), (1, 1))

    def test_index_unique_en_base(self):
        self.ajouter_obs(observation("SPY", "2026-11-02"))
        self.lancer("2026-11-02")
        conn = sqlite3.connect(database.DB_PATH)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO jev_paper_positions (observation_id, ticker, statut, jour_entree, "
                             "prix_entree, quantite, montant_investi, horodatage) "
                             "VALUES (999, 'SPY', 'OPEN', '2026-11-03', 1, 1, 1, 'x')")
        finally:
            conn.close()

    def _rejouer(self, jours_de_cycle: list[str]) -> list[tuple]:
        self.ajouter_obs(observation("SPY", "2026-11-02"), observation("QQQ", "2026-11-03", p_acheter=0.7),
                         observation("SPY", "2026-11-09", p_acheter=0.9))
        self.ajouter_barres("SPY", self.BARRES)
        for jour in jours_de_cycle:
            self.lancer(jour)
        return [(p["ticker"], p["jour_entree"], p["statut"], p["montant_investi"], p["barre_sortie"])
                for p in self.positions()]

    def test_rattrapage_identique_aux_cycles_quotidiens(self):
        un_par_jour = self._rejouer(["2026-11-02", "2026-11-03", "2026-11-09", "2026-11-10"])
        self.tearDown()
        self.setUp()
        rattrapage = self._rejouer(["2026-11-10"])  # cycles des 02, 03 et 09/11 manqués
        self.assertEqual(rattrapage, un_par_jour)
        self.assertEqual(len(un_par_jour), 3)


if __name__ == "__main__":
    unittest.main()
