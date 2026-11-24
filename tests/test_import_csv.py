"""
tests/test_import_csv.py — Import du relevé CSV vers le grand livre (importeurs/revolut_csv.py).

Réécriture en unittest de tests/test_import_csv.py de la source (pytest) : 7 tests, 14 cas
(les deux tests paramétrés de nombre() deviennent 5 et 4 sous-tests), mêmes valeurs attendues.
1. import puis réimport du même fichier : aucun doublon ; frais déduits du total ; le dépôt et
   le dividende du relevé deviennent des mouvements (détail : tests/test_mouvements.py) ;
2. une ligne illisible : rien n'est écrit, l'erreur nomme la ligne ;
3. colonnes absentes signalées ;
4. deux lignes identiques restent deux trades ;
5. colonnes personnalisées, date européenne, devise lue dans le prix ;
6. nombre() : formats lus ; 7. nombre() : montants ambigus ou illisibles refusés.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_import_csv -v
Relevé inventé écrit dans un dossier temporaire ; aucun réseau, aucun .env, rien dans data/.
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
    "2030-01-02T15:00:00.000000Z,aaa,BUY - MARKET,2.5,USD 100.00,USD 251.00,USD,1.10\n"
    "2030-01-05T15:00:00.000000Z,AAA,SELL - MARKET,2.5,$110.00,$274.00,USD,1.12\n"
    "2030-01-06T10:00:00.000000Z,AAA,DIVIDEND,,,USD 1.20,USD,1.12\n")


class TestImport(BaseLedger):
    def ecrire(self, texte):
        chemin = os.path.join(self.dossier.name, "releve.csv")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def test_import_puis_reimport_sans_doublon(self):
        chemin = self.ecrire(CSV)
        r = rc.importer(self.conn, chemin)
        self.assertEqual((r.importes, r.deja_presents, r.erreurs), (2, 0, []))
        self.assertEqual((r.ignores, r.mouvements_importes), ({}, 2))  # dépôt et dividende : mouvements
        r2 = rc.importer(self.conn, chemin)
        self.assertEqual((r2.importes, r2.deja_presents), (0, 2))
        achat, vente = ledger.executions_actives(self.conn)
        self.assertEqual((achat.symbole, achat.sens, achat.quantite, achat.prix, achat.couts),
                         ("AAA", "achat", D("2.5"), D("100.00"), D("1.00")))
        self.assertEqual((vente.sens, vente.prix, vente.couts, vente.devise),
                         ("vente", D("110.00"), D("1.00"), "USD"))
        self.assertEqual(self.conn.execute("SELECT type FROM comptes").fetchone()[0], "reel")

    def test_une_ligne_illisible_et_rien_n_est_ecrit(self):
        mauvais = CSV + "pas-une-date,BBB,BUY - MARKET,1,USD 10,USD 10,USD,1\n"
        r = rc.importer(self.conn, self.ecrire(mauvais))
        self.assertEqual(r.importes, 0)
        self.assertEqual(r.erreurs[0][0], 6)
        self.assertIn("date", r.erreurs[0][1])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 0)

    def test_colonnes_absentes_signalees(self):
        r = rc.importer(self.conn, self.ecrire("Date,Symbol\n2030-01-01,AAA\n"))
        self.assertIn("colonnes absentes", r.erreurs[0][1])
        self.assertIn("Ticker", r.erreurs[0][1])

    def test_deux_lignes_identiques_restent_deux_trades(self):
        ligne = "2030-01-02T15:00:00Z,AAA,BUY - MARKET,1,USD 10,USD 10,USD,1.1\n"
        r = rc.importer(self.conn, self.ecrire(ENTETE + ligne + ligne))
        self.assertEqual(r.importes, 2)
        self.assertEqual(rc.importer(self.conn, self.ecrire(ENTETE + ligne + ligne)).deja_presents, 2)


class TestLecture(unittest.TestCase):
    def test_colonnes_personnalisees_et_date_europeenne(self):
        colonnes = dict(rc.COLONNES, symbole="Symbole", date="Jour")
        flux = io.StringIO("Jour,Symbole,Type,Quantity,Price per share\n"
                           "02/01/2030 15:00:00,AAA,SELL,3,\"€12,30\"\n")
        trades, _, r = rc.lire(flux, colonnes)
        self.assertEqual(r.erreurs, [])
        t = trades[0]
        self.assertEqual((t.sens, t.prix, t.devise, t.frais, t.horodatage.day),
                         ("vente", D("12.30"), "EUR", D("0"), 2))

    def test_nombre(self):
        for texte, attendu in [("USD 1,234.56", "1234.56"), ("$12.30", "12.30"), ("12,30", "12.30"),
                               ("-5.5", "-5.5"), ("€ 0.001", "0.001")]:
            with self.subTest(texte=texte):
                self.assertEqual(rc.nombre(texte), D(attendu))

    def test_nombre_ambigu_ou_illisible(self):
        for texte in ["1,234", "", "abc", "1.2.3"]:
            with self.subTest(texte=texte):
                with self.assertRaises(ValueError):
                    rc.nombre(texte)


if __name__ == "__main__":
    unittest.main()
