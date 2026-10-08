"""
tests/test_jev_fantome.py — Fantôme Jev (REGISTRE_CRITERES §8.2) : entrées, motifs, taille.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_fantome -v
Base SQLite temporaire, valeurs inventées, aucun réseau.
"""

import unittest
from unittest import mock

from tests.jev_fantome_fixtures import BaseFantome, observation, state  # en premier : variables de config.py
import config

JOUR = "2026-11-02"  # lundi


class TestEntrees(BaseFantome):

    def test_achat_au_prix_de_la_ligne(self):
        self.ajouter_obs(observation("SPY", JOUR, p_acheter=0.8, prix=250.0, montant_risque=40.0))
        self.assertEqual(self.lancer(JOUR)["entrees"], 1)
        p, = self.positions()
        self.assertEqual((p["ticker"], p["statut"], p["jour_entree"]), ("SPY", "OPEN", JOUR))
        self.assertEqual(p["prix_entree"], 250.0)  # prix de la ligne, aucun nouvel appel
        self.assertEqual(p["montant_investi"], 40.0)  # facteur 1,0 × 40, sous les plafonds
        self.assertAlmostEqual(p["quantite"], 40.0 / 250.0)

    def test_regle_7_1_pas_d_achat_avec_position_paper_ouverte(self):
        self.ajouter_obs(observation("SPY", JOUR, p_acheter=0.95, position_ouverte=1))
        self.lancer(JOUR)
        self.assertEqual(self.positions(), [])
        self.assertEqual(self.refus(), {"SPY": "position_paper_ouverte"})

    def test_motifs_sans_achat(self):
        cas = {
            "conviction_nulle": {"conviction_niveau": 0},
            "sans_prix": {"prix": None},
            "sans_montant_risque": {"montant_risque": None, "state": state(None)},
            "montant_vente_a_decouvert": {"state": state("SHORT")},
            "sans_mode_bm": {"mode_bm": None},
        }
        for i, (motif, champs) in enumerate(cas.items()):
            with self.subTest(motif=motif):
                ticker = f"T{i}"
                self.ajouter_obs(observation(ticker, JOUR, p_acheter=0.9, **champs))
                self.lancer(JOUR)
                self.assertEqual(self.refus()[ticker], motif)
        self.assertEqual(self.positions(), [])

    def test_conviction_nulle_enregistree_meme_avec_p_eleve(self):
        self.ajouter_obs(observation("NVDA", JOUR, p_acheter=0.99, conviction_niveau=0))
        self.lancer(JOUR)
        self.assertEqual(self.refus(), {"NVDA": "conviction_nulle"})

    def test_sous_le_seuil_rien_n_est_enregistre(self):
        self.ajouter_obs(observation("SPY", JOUR, p_acheter=0.59))
        self.assertEqual(self.lancer(JOUR)["entrees"], 0)
        self.assertEqual((self.positions(), self.lire("jev_paper_journal")), ([], []))

    def test_facteurs_de_conviction(self):
        # 80 € de référence : 16 € puis 40 €, sous le plafond par trade (10 % du cash libre)
        for niveau, attendu in ((1, 0.2 * 80), (2, 0.5 * 80)):
            with self.subTest(niveau=niveau):
                t = f"C{niveau}"
                self.ajouter_obs(observation(t, JOUR, conviction_niveau=niveau, montant_risque=80.0))
                self.lancer(JOUR)
                self.assertEqual({p["ticker"]: p["montant_investi"] for p in self.positions()}[t], attendu)

    def test_plafond_par_trade_et_ordre_par_p_acheter(self):
        # NORMAL : 500 € investissables, 10 % du cash libre par trade
        self.ajouter_obs(observation("AAA", JOUR, p_acheter=0.7, montant_risque=400.0),
                         observation("BBB", JOUR, p_acheter=0.9, montant_risque=400.0))
        self.lancer(JOUR)
        tailles = {p["ticker"]: p["montant_investi"] for p in self.positions()}
        self.assertEqual(tailles, {"BBB": 50.0, "AAA": 45.0})  # BBB d'abord (p plus élevé)

    def test_plafond_du_mode_defensif(self):
        self.ajouter_obs(observation("SPY", JOUR, mode_bm="DEFENSIF", montant_risque=400.0))
        self.lancer(JOUR)
        self.assertEqual(self.positions()[0]["montant_investi"], 60.0)  # 20 % de 300 €

    def test_nombre_maximal_de_positions(self):
        self.ajouter_obs(observation("AAA", JOUR, p_acheter=0.7), observation("BBB", JOUR, p_acheter=0.9))
        with mock.patch.object(config, "MAX_POSITIONS_SIMULTANEES", 1):
            self.lancer(JOUR)
        self.assertEqual([p["ticker"] for p in self.positions()], ["BBB"])
        self.assertEqual(self.refus(), {"AAA": "max_positions"})

    def test_sous_le_minimum_viable(self):
        self.ajouter_obs(observation("SPY", JOUR, montant_risque=14.0))
        self.lancer(JOUR)
        self.assertEqual(self.refus(), {"SPY": "sous_minimum"})

    def test_cash_libre_epuise(self):
        # 500 € investissables : 20 achats successifs à 10 % du cash libre font tomber le plafond sous 15 €
        jours = [f"2026-11-{j:02d}" for j in range(2, 27)]
        self.ajouter_obs(*[observation(f"A{i:02d}", j, montant_risque=1000.0) for i, j in enumerate(jours)])
        self.lancer(jours[-1])
        investi = sum(p["montant_investi"] for p in self.positions())
        self.assertLessEqual(investi, 500.0)
        self.assertIn("sous_minimum", self.refus().values())


class TestSelection(BaseFantome):
    """Seules les observations du §7.1 alimentent le fantôme."""

    def test_autre_modele_erreur_autre_cycle_ignores(self):
        self.ajouter_obs(observation("AAA", JOUR, modele="jev-1.14.0"),
                         observation("BBB", JOUR, statut="erreur"),
                         observation("CCC", JOUR, cycle="tactical"),
                         observation("DDD", JOUR, questions_version="v2"))
        self.lancer(JOUR)
        self.assertEqual((self.positions(), self.lire("jev_paper_journal")), ([], []))

    def test_premiere_observation_du_jour_seulement(self):
        self.ajouter_obs(observation("SPY", JOUR, p_acheter=0.1),
                         dict(observation("SPY", JOUR, p_acheter=0.9), horodatage=f"{JOUR}T09:00:00+00:00"))
        self.lancer(JOUR)
        self.assertEqual(self.positions(), [])

    def test_observation_posterieure_au_jour_traite_ignoree(self):
        self.ajouter_obs(observation("SPY", "2026-11-03"))
        self.lancer(JOUR)
        self.assertEqual(self.positions(), [])


if __name__ == "__main__":
    unittest.main()
