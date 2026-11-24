"""
tests/test_import_mouvements.py — Relevé CSV Revolut : DIVIDEND, CASH TOP-UP et CASH WITHDRAWAL
deviennent des mouvements du grand livre (importeurs/revolut_csv.py, revolut_lecture.py).

1. les trois types sont inscrits, un retrait négatif par sa valeur absolue, le dividende avec
   son titre ; les autres types restent ignorés et comptés ; réimport sans doublon ;
2. tout ou rien : un mouvement illisible (montant absent, nul, dépôt négatif, date) et ni
   trade ni mouvement n'est écrit ;
3. deux lignes identiques restent deux mouvements ; devise lue dans le montant ;
4. aperçu : compte ce qui serait ajouté sans rien écrire, avec ou sans grand livre ;
5. importer_flux lit un relevé gardé en mémoire (aucun fichier).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_import_mouvements -v
Relevé inventé, base dans un dossier temporaire ; aucun réseau, aucun .env, rien dans data/.
"""

import io
import os
import sys
import unittest
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from importeurs import revolut_csv as rc
from tests.socle_fixtures import BaseLedger

ENTETE = "Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate\n"
CSV = ENTETE + (
    "2030-01-02T14:30:00.000000Z,,CASH TOP-UP,,,USD 500,USD,1.10\n"
    "2030-01-02T15:00:00.000000Z,AAA,BUY - MARKET,2.5,USD 100.00,USD 251.00,USD,1.10\n"
    "2030-01-05T15:00:00.000000Z,AAA,SELL - MARKET,2.5,$110.00,$274.00,USD,1.12\n"
    "2030-01-06T10:00:00.000000Z,AAA,DIVIDEND,,,USD 1.20,USD,1.12\n"
    "2030-01-07T09:00:00.000000Z,,CUSTODY FEE,,,USD -0.12,USD,1.12\n"
    "2030-01-08T09:00:00.000000Z,AAA,STOCK SPLIT,5,,,USD,1.12\n"
    "2030-01-09T11:00:00.000000Z,,CASH WITHDRAWAL,,,USD -120.50,USD,1.11\n")


def importer(conn, texte):
    return rc.importer_flux(conn, io.StringIO(texte))


class TestImport(BaseLedger):
    def compte_id(self):
        return ledger.comptes(self.conn)[0].id

    def test_trois_types_inscrits_puis_reimport_sans_doublon(self):
        r = importer(self.conn, CSV)
        self.assertEqual((r.importes, r.mouvements_importes, r.mouvements_deja_presents, r.erreurs), (2, 3, 0, []))
        self.assertEqual(r.ignores, {"CUSTODY FEE": 1, "STOCK SPLIT": 1})
        depot, dividende, retrait = ledger.mouvements(self.conn, self.compte_id())
        self.assertEqual((depot.type, depot.montant, depot.devise, depot.symbole), ("depot", D("500"), "USD", None))
        self.assertEqual((dividende.type, dividende.montant, dividende.symbole), ("dividende", D("1.20"), "AAA"))
        self.assertEqual((retrait.type, retrait.montant, retrait.horodatage.day), ("retrait", D("120.50"), 9))
        r2 = importer(self.conn, CSV)
        self.assertEqual((r2.importes, r2.deja_presents, r2.mouvements_importes, r2.mouvements_deja_presents),
                         (0, 2, 0, 3))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM mouvements").fetchone()[0], 3)
        self.assertEqual(ledger.comptes(self.conn)[0].nom, rc.COMPTE)

    def test_un_mouvement_illisible_et_rien_n_est_ecrit(self):
        for ligne, attendu in [("2030-01-10T09:00:00Z,,CASH TOP-UP,,,,USD,1.1\n", "montant absent"),
                               ("2030-01-10T09:00:00Z,,CASH WITHDRAWAL,,,USD 0,USD,1.1\n", "nul ou négatif"),
                               ("2030-01-10T09:00:00Z,,CASH TOP-UP,,,USD -50,USD,1.1\n", "nul ou négatif"),
                               ("2030-01-10T09:00:00Z,AAA,DIVIDEND,,,USD -1,USD,1.1\n", "nul ou négatif"),
                               ("pas-une-date,AAA,DIVIDEND,,,USD 1,USD,1.1\n", "date illisible"),
                               ("2030-01-10T09:00:00Z,,CASH TOP-UP,,,500,,1.1\n", "devise absente")]:
            with self.subTest(ligne=ligne):
                r = importer(self.conn, CSV + ligne)
                self.assertEqual((r.importes, r.mouvements_importes), (0, 0))
                self.assertEqual(r.erreurs[0][0], 9)  # numéro de ligne dans le fichier
                self.assertIn(attendu, r.erreurs[0][1])
                for table in ("trades", "mouvements", "comptes"):
                    self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_lignes_identiques_et_devise_lue_dans_le_montant(self):
        ligne = "2030-01-02T14:30:00Z,,CASH TOP-UP,,,€ 100,,\n"
        r = importer(self.conn, ENTETE + ligne + ligne)
        self.assertEqual(r.mouvements_importes, 2)
        self.assertEqual({(m.montant, m.devise) for m in ledger.mouvements(self.conn, self.compte_id())},
                         {(D("100"), "EUR")})
        self.assertEqual(importer(self.conn, ENTETE + ligne + ligne).mouvements_deja_presents, 2)

    def test_un_type_voisin_reste_ignore(self):
        r = importer(self.conn, ENTETE + "2030-01-06T10:00:00Z,AAA,DIVIDEND TAX (CORRECTION),,,USD 0.20,USD,1.1\n")
        self.assertEqual((r.ignores, r.mouvements_importes), ({"DIVIDEND TAX (CORRECTION)": 1}, 0))


class TestApercu(BaseLedger):
    def test_apercu_ne_cree_ni_n_ecrit_rien(self):
        r = rc.apercu(None, io.StringIO(CSV))  # pas encore de grand livre : tout est à ajouter
        self.assertEqual((r.importes, r.deja_presents, r.mouvements_importes, r.mouvements_deja_presents),
                         (2, 0, 3, 0))
        chemin = os.path.join(self.dossier.name, "ledger.db")
        lecture = ledger.ouvrir_lecture(chemin)
        self.addCleanup(lecture.close)
        self.assertEqual(rc.apercu(lecture, io.StringIO(CSV)).importes, 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 0)
        importer(self.conn, CSV)
        plus = CSV + "2030-01-10T09:00:00Z,,CASH TOP-UP,,,USD 40,USD,1.1\n"
        r = rc.apercu(lecture, io.StringIO(plus))
        self.assertEqual((r.importes, r.deja_presents, r.mouvements_importes, r.mouvements_deja_presents),
                         (0, 2, 1, 3))
        self.assertEqual(r.ignores, {"CUSTODY FEE": 1, "STOCK SPLIT": 1})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM mouvements").fetchone()[0], 3)

    def test_apercu_avec_erreur_garde_le_numero_de_ligne(self):
        r = rc.apercu(None, io.StringIO(CSV + "pas-une-date,BBB,BUY - MARKET,1,USD 10,USD 10,USD,1\n"))
        self.assertEqual([n for n, _ in r.erreurs], [9])
        self.assertEqual((r.importes, r.mouvements_importes), (2, 3))  # ce qui a pu être lu


if __name__ == "__main__":
    unittest.main()
