"""
tests/test_pro_synchro_cours.py — Bouton « Synchroniser » : troisième étape, les cours de clôture.

1. après les positions paper et les taux, les clôtures de chaque instrument négocié sont
   inscrites ; un symbole introuvable est listé ; relancer n'ajoute rien ;
2. un échec des cours n'annule pas les deux premières étapes : positions et taux restent écrits,
   le rapport dit ce qui a été écrit et ce qui a échoué ;
3. un refus des deux premières étapes : aucun cours demandé, rien n'est écrit.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_synchro_cours -v
Bases temporaires, positions et cours inventés ; aucun réseau (toute connexion lève une erreur).
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal as D
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from importeurs import cours as ic
from importeurs import taux_change as tc
from tests.test_pro_synchro import BaseSynchro

INTROUVABLE = [["BBB", "aucune barre entre 2026-11-02 et 2026-11-09"]]


class TestCoursApresPositionsEtTaux(BaseSynchro):
    def test_cours_inscrits_et_symbole_introuvable_liste(self):
        self.positions()  # AAA fermée, BBB ouverte, CCC « boucle » (jamais importée)
        j = self.synchroniser().get_json()
        self.assertEqual(j["cours"], {"ok": True, "instruments": 2, "ajoutes": 2, "deja_presents": 0, "ecartes": 0,
                                      "a_jour": [], "introuvables": INTROUVABLE})
        self.assertEqual(self.source_cours.appels, [("AAA", date(2026, 11, 2), date(2026, 11, 9)),
                                                    ("BBB", date(2026, 11, 2), date(2026, 11, 9))])
        self.assertEqual([(c.symbole, c.jour, c.cloture, c.devise) for c in ledger.cours(self.conn)],
                         [("AAA", date(2026, 11, 2), D("100"), "USD"), ("AAA", date(2026, 11, 9), D("108"), "USD")])
        j = self.synchroniser().get_json()  # relance : rien de plus
        self.assertEqual((j["cours"]["ajoutes"], j["cours"]["deja_presents"], self.compte("cours")), (0, 2, 2))

    def test_echec_des_cours_n_annule_pas_positions_et_taux(self):
        self.positions()
        with mock.patch.object(ic, "importer", side_effect=RuntimeError("disque plein")):
            r = self.synchroniser()
        j = r.get_json()
        self.assertEqual((r.status_code, j["ok"], j["paper"]["importes"], j["taux"]["ajoutes"]), (200, True, 3, 2))
        self.assertEqual(j["cours"], {"ok": False, "message": "RuntimeError : disque plein. Aucun cours n'a été écrit."})
        self.assertEqual((self.compte("trades"), self.compte("change"), self.compte("cours")), (3, 2, 0))
        j = self.synchroniser().get_json()  # la cause levée, seuls les cours manquaient
        self.assertEqual((j["paper"]["importes"], j["taux"]["ajoutes"], j["cours"]["ajoutes"]), (0, 0, 2))

    def test_erreur_au_milieu_des_cours_rien_des_cours_n_est_ecrit(self):
        self.positions()
        with mock.patch.object(ledger.ecriture, "enregistrer_cours", side_effect=[1, RuntimeError("coupure")]):
            j = self.synchroniser().get_json()
        self.assertEqual((j["ok"], j["cours"]["ok"]), (True, False))
        self.assertEqual((self.compte("trades"), self.compte("change"), self.compte("cours")), (3, 2, 0))

    def test_refus_des_deux_premieres_etapes_aucun_cours_demande(self):
        self.positions()

        def en_panne(debut, fin):
            raise tc.SourceIndisponible("cours EURUSD=X indisponible : réseau coupé")
        with mock.patch.object(tc, "cloture_yfinance", en_panne):
            self.refus("cours EURUSD=X indisponible : réseau coupé")
        self.assertEqual((self.source_cours.appels, self.compte("cours")), ([], 0))


if __name__ == "__main__":
    unittest.main()
