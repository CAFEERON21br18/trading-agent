"""
tests/test_pro_synchro.py — Bouton « Synchroniser » (POST /pro/synchroniser, dashboard/pro/synchro.py).

1. positions paper puis taux EURUSD, en mode appliquer ; le rapport des deux ; relancer n'ajoute
   rien ; une position marquée « boucle » après son import est annulée ;
2. colonne « boucle » absente, position illisible, cours indisponible, erreur pendant l'écriture :
   RIEN n'est écrit (ni positions ni taux), le message est rendu tel quel ;
3. en-tête X-AlphaSignal et POST exigés ; la base de l'agent n'est jamais modifiée ;
4. valider=False (importeurs) : la transaction reste à l'appelant ;
5. aucune tâche planifiée ne lance la synchronisation.
Le script du bouton est testé dans tests/test_pro_synchro_page.py.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_synchro -v
Bases temporaires, positions et cours inventés ; aucun réseau (toute connexion lève une erreur).
"""

import glob
import os
import sqlite3
import sys
import unittest
from datetime import date
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from importeurs import paper
from importeurs import taux_change as tc
from tests.pro_fixtures import AUJOURD_HUI, empreinte
from tests.pro_page_fixtures import EN_TETE, BasePage
from tests.socle_paper_fixtures import creer_base, executer, position
from tests.socle_taux_fixtures import source
from utils import database

COURS = [(date(2026, 11, 6), 1.25), (date(2026, 11, 9), 1.26), (AUJOURD_HUI, 1.27)]  # le jour en cours : hors période
ENTREE, SORTIE = "2026-11-02T10:00:00+00:00", "2026-11-03T15:30:00+00:00"


class BaseSynchro(BasePage):
    def setUp(self):
        super().setUp()
        self.source = source(COURS)
        for cible, nom, valeur in ((tc, "cloture_yfinance", self.source),):
            correctif = mock.patch.object(cible, nom, valeur)
            correctif.start()
            self.addCleanup(correctif.stop)
        piege = mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))
        piege.start()
        self.addCleanup(piege.stop)

    def synchroniser(self, entetes=EN_TETE):
        return self.client.post("/pro/synchroniser", headers=entetes)

    def compte(self, table="trades") -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def positions(self):
        fermee = position(self.base, "AAA", prix=100.0, sortie=110.0, quantite=2.0, entree_le=ENTREE, sortie_le=SORTIE)
        ouverte = position(self.base, "BBB", statut="OPEN", entree_le=ENTREE)
        position(self.base, "CCC", boucle=1, entree_le=ENTREE, sortie_le=SORTIE)
        return fermee, ouverte

    def refus(self, attendu: str):
        """La synchronisation est refusée avec ce message, et le grand livre n'a pas bougé."""
        avant = empreinte(self.chemin_ledger)
        r = self.synchroniser()
        self.assertEqual((r.status_code, r.get_json()), (409, {"ok": False, "message": attendu}))
        self.assertEqual((empreinte(self.chemin_ledger), self.compte("trades"), self.compte("change")), (avant, 0, 0))


class TestSynchronisation(BaseSynchro):
    def test_positions_puis_taux_et_rapport(self):
        self.positions()
        base_avant = empreinte(self.base)
        r = self.synchroniser()
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual((j["ok"], j["paper"]), (True, {"positions": 2, "boucles": 1, "importes": 3, "deja_presents": 0,
                                                       "annules": 0, "devises_incertaines": [], "erreurs": []}))
        self.assertEqual(j["taux"], {"ajoutes": 2, "deja_presents": 0, "ecartes": 0, "premier": "2026-11-06",
                                     "dernier": "2026-11-09"})
        self.assertEqual((self.compte("trades"), self.compte("change")), (3, 2))
        self.assertEqual([(c.nom, c.type) for c in ledger.comptes(self.conn)], [("Paper agent", "paper")])
        self.assertEqual(self.source.appels, [(date(2025, 11, 10), date(2026, 11, 9))])  # 365 jours, jusqu'à hier
        self.assertEqual(empreinte(self.base), base_avant)  # base de l'agent : lecture seule
        j = self.synchroniser().get_json()  # relance : rien de plus
        self.assertEqual((j["paper"]["importes"], j["paper"]["deja_presents"], j["taux"]["ajoutes"],
                          j["taux"]["deja_presents"]), (0, 3, 0, 2))
        self.assertEqual((self.compte("trades"), self.compte("change")), (3, 2))
        self.assertIn("+20,00", self.section(self.page("/pro?devise=USD"), "compte-paper"))  # la page le montre

    def test_position_marquee_boucle_apres_import_annulee(self):
        fermee, _ = self.positions()
        self.synchroniser()
        executer(self.base, "UPDATE positions SET boucle = 1 WHERE id = ?", (fermee,))
        j = self.synchroniser().get_json()
        self.assertEqual((j["paper"]["annules"], j["paper"]["boucles"]), (2, 2))
        self.assertEqual((self.compte("trades"), len(ledger.executions_actives(self.conn))), (5, 1))  # rien d'effacé

    def test_sans_grand_livre_il_est_cree_par_la_synchronisation_reussie(self):
        absent = self.sans_grand_livre()
        os.makedirs(os.path.dirname(absent))
        self.positions()
        self.assertTrue(self.synchroniser().get_json()["ok"])
        self.assertTrue(os.path.isfile(absent))


class TestRienNEstEcrit(BaseSynchro):
    def test_colonne_boucle_absente(self):
        sans_colonne = os.path.join(self.dossier.name, "sans_boucle.db")
        creer_base(sans_colonne, boucle=False)  # base jamais marquée par scripts/marquer_boucles.py
        with mock.patch.object(database, "DB_PATH", sans_colonne):
            self.refus("colonne « boucle » absente de la table positions : lancer d'abord"
                       " scripts/marquer_boucles.py --appliquer. Rien n'a été importé.")
            absent = self.sans_grand_livre()
            os.makedirs(os.path.dirname(absent))
            self.assertEqual(self.synchroniser().status_code, 409)
            self.assertEqual(os.listdir(os.path.dirname(absent)), [])  # le grand livre n'est pas créé
        self.assertEqual(self.source.appels, [])  # aucun cours demandé

    def test_position_illisible(self):
        self.positions()
        mauvaise = position(self.base, "DDD", direction="DIAGONALE", entree_le=ENTREE, sortie_le=SORTIE)
        self.refus(f"positions illisibles, rien n'a été écrit : position #{mauvaise} : direction inconnue : 'DIAGONALE'")
        self.assertEqual(self.source.appels, [])

    def test_cours_indisponible(self):
        self.positions()

        def en_panne(debut, fin):
            raise tc.SourceIndisponible("cours EURUSD=X indisponible : réseau coupé")
        with mock.patch.object(tc, "cloture_yfinance", en_panne):
            self.refus("cours EURUSD=X indisponible : réseau coupé")  # les positions non plus ne sont pas écrites

    def test_erreur_pendant_l_ecriture_tout_est_annule(self):
        self.positions()
        with mock.patch.object(ledger.ecriture, "enregistrer_taux", side_effect=RuntimeError("disque plein")):
            self.refus("RuntimeError : disque plein. Rien n'a été écrit.")
        self.assertTrue(self.synchroniser().get_json()["ok"])  # la cause levée, tout passe
        self.assertEqual((self.compte("trades"), self.compte("change")), (3, 2))

    def test_en_tete_et_methode(self):
        self.positions()
        self.assertEqual(self.synchroniser(entetes={}).status_code, 403)
        self.assertEqual(self.client.get("/pro/synchroniser").status_code, 405)
        self.assertEqual((self.compte("trades"), self.source.appels), (0, []))


class TestTransactionALAppelant(BaseSynchro):
    def test_valider_false_laisse_la_transaction_ouverte(self):
        self.positions()
        temoin = sqlite3.connect(self.chemin_ledger)
        self.addCleanup(temoin.close)
        vus = lambda: (temoin.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
                       temoin.execute("SELECT COUNT(*) FROM change").fetchone()[0])
        r = paper.synchroniser(self.conn, self.base, appliquer=True, valider=False)
        tc.importer(self.conn, date(2026, 11, 1), date(2026, 11, 9), source(COURS), aujourd_hui=AUJOURD_HUI,
                    valider=False)
        self.assertEqual((r.importes, vus()), (3, (0, 0)))  # écrit, pas encore validé
        self.conn.rollback()
        self.assertEqual((self.compte("trades"), self.compte("change")), (0, 0))
        paper.synchroniser(self.conn, self.base)  # par défaut : validé, comme avant
        self.assertEqual(vus(), (3, 0))

    def test_aucune_tache_planifiee(self):
        scripts = glob.glob(os.path.join(RACINE, "scripts", "*.ps1")) + glob.glob(os.path.join(RACINE, "scripts", "cycle_*.py"))
        self.assertGreaterEqual(len(scripts), 7)
        for chemin in scripts:
            with self.subTest(script=os.path.basename(chemin)), open(chemin, encoding="utf-8", errors="replace") as f:
                texte = f.read().lower()
                for interdit in ("pro/synchroniser", "ledger", "dashboard.pro", "synchro.py"):
                    self.assertNotIn(interdit, texte)


if __name__ == "__main__":
    unittest.main()
