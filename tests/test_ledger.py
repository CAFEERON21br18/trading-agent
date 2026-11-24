"""
tests/test_ledger.py — Grand livre en écriture seule (ledger/).

Réécriture en unittest de tests/test_ledger.py de la source (pytest) : 8 tests, 14 cas
(le test paramétré sur les 7 tables devient 7 sous-tests), mêmes valeurs attendues.
1. UPDATE et DELETE refusés sur chacune des 7 tables ;
2. un trade déjà présent (même source, même référence) n'est pas réécrit ;
3. valeurs invalides refusées avant d'atteindre la base ;
4. coûts et contexte d'entrée relus ; correction et annulation par une nouvelle ligne ;
5. filtre par compte ; la dernière saisie du jour l'emporte (taux, valeur quotidienne).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_ledger -v
Base dans un dossier temporaire, données inventées ; aucun réseau, aucun .env.
"""

import os
import sqlite3
import sys
import unittest
from datetime import date
from decimal import Decimal

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from tests.socle_fixtures import BaseLedgerIds, ids_de_test, trade


class TestLedger(BaseLedgerIds):
    def test_update_et_delete_refuses(self):
        for table in ledger.TABLES:
            with self.subTest(table=table):
                conn = self.nouvelle_base(f"{table}.db")
                ids = ids_de_test(conn)
                trade(conn, ids, "a", couts=[("commission", "1")], contexte={"bras": "regles"})
                ledger.enregistrer_taux(conn, date(2030, 1, 1), "1.10", "test")
                ledger.enregistrer_valeur(conn, ids[0], date(2030, 1, 1), "1000", "USD")
                with self.assertRaisesRegex(sqlite3.IntegrityError, "ecriture seule"):
                    conn.execute(f"UPDATE {table} SET id = id")
                with self.assertRaisesRegex(sqlite3.IntegrityError, "ecriture seule"):
                    conn.execute(f"DELETE FROM {table}")

    def test_trade_idempotent(self):
        self.assertIsNotNone(trade(self.conn, self.ids, "a"))
        self.assertIsNone(trade(self.conn, self.ids, "a"))
        self.assertEqual(len(ledger.executions_actives(self.conn)), 1)

    def test_valeurs_invalides_refusees(self):
        for kw in ({"q": "0"}, {"prix": "-1"}, {"q": "abc"}, {"sens": "long"}):
            with self.assertRaises(ledger.EcritureInvalide):
                trade(self.conn, self.ids, "x", **kw)
        self.assertEqual(ledger.executions_actives(self.conn), [])

    def test_lecture_couts_et_contexte(self):
        trade(self.conn, self.ids, "a", couts=[("commission", "1.5"), ("spread", "0.5")],
              contexte={"bras": "regles", "stop_initial": "95"})
        ex = ledger.executions_actives(self.conn)[0]
        self.assertEqual((ex.symbole, ex.quantite, ex.prix), ("AAA", Decimal("10"), Decimal("100")))
        self.assertEqual(ex.couts, Decimal("2.0"))
        self.assertEqual(ex.stop_initial, Decimal("95"))
        self.assertEqual(ex.bras, "regles")

    def test_correction_remplace_sans_effacer(self):
        ancien = trade(self.conn, self.ids, "a", couts=[("commission", "1")],
                       contexte={"stop_initial": "95"})
        nouveau = ledger.corriger_trade(self.conn, ancien, prix="101")
        actives = ledger.executions_actives(self.conn)
        self.assertEqual([e.id for e in actives], [nouveau])
        self.assertEqual(actives[0].prix, Decimal("101"))
        self.assertEqual(actives[0].couts, Decimal("1"))
        self.assertEqual(actives[0].stop_initial, Decimal("95"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 2)
        with self.assertRaises(ledger.EcritureInvalide):
            ledger.corriger_trade(self.conn, ancien, prix="102")
        with self.assertRaises(ledger.EcritureInvalide):
            ledger.corriger_trade(self.conn, nouveau, compte_id=9)

    def test_annulation(self):
        a = trade(self.conn, self.ids, "a")
        trade(self.conn, self.ids, "b", j=2)
        ledger.annuler_trade(self.conn, a)
        self.assertEqual([e.horodatage.day for e in ledger.executions_actives(self.conn)], [2])
        with self.assertRaises(ledger.EcritureInvalide):
            ledger.annuler_trade(self.conn, a)

    def test_filtre_par_compte(self):
        trade(self.conn, self.ids, "a")
        autre = ledger.compte(self.conn, "Autre", "demo", "EUR")
        self.assertEqual(ledger.executions_actives(self.conn, autre), [])
        self.assertEqual(len(ledger.executions_actives(self.conn, self.ids[0])), 1)

    def test_derniere_saisie_du_jour_l_emporte(self):
        j = date(2030, 1, 1)
        ledger.enregistrer_taux(self.conn, j, "1.10", "test")
        ledger.enregistrer_taux(self.conn, j, "1.12", "test")
        self.assertEqual(ledger.taux_eurusd(self.conn), {j: Decimal("1.12")})
        ledger.enregistrer_valeur(self.conn, self.ids[0], j, "1000", "USD")
        ledger.enregistrer_valeur(self.conn, self.ids[0], j, "1010", "USD")
        self.assertEqual(ledger.valeurs_quotidiennes(self.conn, self.ids[0]), [(j, Decimal("1010"))])


if __name__ == "__main__":
    unittest.main()
