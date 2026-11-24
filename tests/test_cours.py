"""
tests/test_cours.py — Cours de clôture dans le grand livre (table cours, ledger/).

1. enregistrer_cours : pas de doublon pour un jour déjà présent avec la même clôture ; une
   clôture différente ajoute une ligne et la dernière saisie l'emporte à la lecture ; valeurs
   invalides refusées ;
2. lecture des cours d'un instrument, dernier cours de chaque instrument ;
3. la table se crée sur un grand livre existant (7 tables, ou 8 avec mouvements) sans rien
   toucher d'autre ; en lecture seule sur un ancien grand livre, elle est lue comme vide ;
4. instruments négociés : jour du premier trade actif ;
5. copie en mémoire : y écrire ne touche pas au fichier.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_cours -v
Bases dans un dossier temporaire, cours inventés ; aucun réseau, aucun .env, rien dans data/.
"""

import os
import sqlite3
import sys
import unittest
from datetime import date
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from tests import socle_ancien_schema, socle_schema_8_tables
from tests.pro_fixtures import empreinte
from tests.socle_fixtures import BaseLedgerIds, jour, trade


def cours(conn, instrument_id, j, cloture, devise="USD", source="test"):
    return ledger.enregistrer_cours(conn, instrument_id=instrument_id, jour=date(2030, 1, j), cloture=cloture,
                                    devise=devise, source=source)


class TestEcritureEtLecture(BaseLedgerIds):
    def test_sans_doublon_et_derniere_saisie(self):
        aaa = self.ids[1]
        self.assertIsNotNone(cours(self.conn, aaa, 3, "101.5"))
        self.assertIsNone(cours(self.conn, aaa, 3, "101.50"))  # même clôture : rien n'est ajouté
        self.assertIsNotNone(cours(self.conn, aaa, 3, "102"))  # clôture corrigée : une ligne de plus
        self.assertIsNotNone(cours(self.conn, aaa, 2, "100"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cours").fetchone()[0], 3)
        self.assertEqual(ledger.cours(self.conn, "aaa"),
                         [ledger.Cours("AAA", date(2030, 1, 2), D("100"), "USD", "test"),
                          ledger.Cours("AAA", date(2030, 1, 3), D("102"), "USD", "test")])
        self.assertIsNotNone(cours(self.conn, aaa, 3, "101.5"))  # retour à l'ancienne valeur : ajouté
        self.assertIsNone(cours(self.conn, aaa, 3, "101.5"))
        self.assertEqual(ledger.cours(self.conn, "AAA")[-1].cloture, D("101.5"))

    def test_dernier_cours_par_instrument(self):
        bbb = ledger.instrument(self.conn, "BBB.PA", "EUR")
        cours(self.conn, self.ids[1], 8, "110")
        cours(self.conn, self.ids[1], 6, "105")
        cours(self.conn, bbb, 7, "20.5", devise="eur")
        ledger.instrument(self.conn, "CCC", "USD")  # aucun cours
        derniers = ledger.derniers_cours(self.conn)
        self.assertEqual({s: (c.jour, c.cloture, c.devise) for s, c in derniers.items()},
                         {"AAA": (date(2030, 1, 8), D("110"), "USD"), "BBB.PA": (date(2030, 1, 7), D("20.5"), "EUR")})
        self.assertEqual([c.symbole for c in ledger.cours(self.conn)], ["AAA", "AAA", "BBB.PA"])
        self.assertEqual(ledger.cours(self.conn, "CCC"), [])

    def test_valeurs_invalides_refusees(self):
        for cloture in ("0", "-1", "abc", float("nan")):
            with self.subTest(cloture=cloture), self.assertRaises(ledger.EcritureInvalide):
                cours(self.conn, self.ids[1], 3, cloture)
        self.assertEqual(ledger.cours(self.conn), [])

    def test_instruments_negocies_et_premier_trade(self):
        bbb = ledger.instrument(self.conn, "BBB", "EUR")
        ledger.instrument(self.conn, "CCC", "USD")  # jamais négocié
        trade(self.conn, self.ids, "a", j=5)
        trade(self.conn, self.ids, "b", sens="vente", j=7)
        annule = trade(self.conn, (self.ids[0], bbb), "c", j=2)
        trade(self.conn, (self.ids[0], bbb), "d", j=6)
        ledger.annuler_trade(self.conn, annule)
        self.assertEqual(ledger.instruments_negocies(self.conn),
                         [(self.ids[1], "AAA", "USD", date(2030, 1, 5)), (bbb, "BBB", "EUR", date(2030, 1, 6))])


def etat(conn, tables) -> tuple:
    """Schéma et contenu des tables d'un ancien grand livre."""
    marques = ", ".join("?" * len(tables))
    schema = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"
                          f" WHERE tbl_name IN ({marques}) ORDER BY name", tables).fetchall()
    return ([tuple(l) for l in schema],
            {t: [tuple(l) for l in conn.execute(f"SELECT * FROM {t} ORDER BY id")] for t in tables})


class TestBaseExistante(BaseLedgerIds):
    def ancienne_base(self, ancien) -> str:
        chemin = os.path.join(self.dossier.name, f"ancien_{len(ancien.TABLES)}.db")
        conn = ancien.creer_ancien(chemin)
        ids = (ledger.compte(conn, "Paper agent", "paper", "EUR"), ledger.instrument(conn, "AAA", "USD"))
        trade(conn, ids, "a", couts=[("commission", "1")], contexte={"bras": "regles", "stop_initial": "95"})
        trade(conn, ids, "b", sens="vente", prix="110", j=3)
        ledger.enregistrer_taux(conn, date(2030, 1, 3), "1.10", "test")
        ledger.enregistrer_valeur(conn, ids[0], date(2030, 1, 3), "1000", "EUR")
        if "mouvements" in ancien.TABLES:
            ledger.enregistrer_mouvement(conn, compte_id=ids[0], horodatage=jour(2), type_="depot", montant="500",
                                         devise="EUR", source="test", ref_source="m")
        conn.commit()
        conn.close()
        return chemin

    def test_la_table_se_cree_sans_rien_toucher_d_autre(self):
        for ancien in (socle_ancien_schema, socle_schema_8_tables):
            with self.subTest(tables=len(ancien.TABLES)):
                chemin = self.ancienne_base(ancien)
                lecture = ledger.ouvrir_lecture(chemin)
                self.assertEqual((ledger.cours(lecture), ledger.derniers_cours(lecture)), ([], {}))  # table absente
                lecture.close()
                brut = sqlite3.connect(chemin)
                self.addCleanup(brut.close)
                avant = etat(brut, ancien.TABLES)
                self.assertEqual(len(avant[1]["trades"]), 2)
                conn = ledger.ouvrir(chemin)
                self.addCleanup(conn.close)
                self.assertEqual(etat(brut, ancien.TABLES), avant)  # mêmes tables, index, déclencheurs, lignes
                noms = {l[0] for l in brut.execute("SELECT name FROM sqlite_master WHERE tbl_name = 'cours'")}
                self.assertEqual(noms, {"cours", "cours_sans_modif", "cours_sans_suppr", "idx_cours_instrument"})
                aaa = ledger.instruments_negocies(conn)[0][0]
                cours(conn, aaa, 3, "110")
                for requete in ("UPDATE cours SET cloture = '1'", "DELETE FROM cours"):
                    with self.assertRaisesRegex(sqlite3.IntegrityError, "ecriture seule"):
                        conn.execute(requete)
                conn.commit()
                ledger.ouvrir(chemin).close()  # une seconde ouverture ne change rien non plus
                self.assertEqual(etat(brut, ancien.TABLES), avant)
                self.assertEqual(len(ledger.cours(conn, "AAA")), 1)

    def test_copie_en_memoire_ne_touche_pas_au_fichier(self):
        chemin = self.ancienne_base(socle_schema_8_tables)
        avant = empreinte(chemin)
        copie = ledger.copie_en_memoire(chemin)
        self.addCleanup(copie.close)
        aaa = ledger.instruments_negocies(copie)[0][0]
        cours(copie, aaa, 3, "110")
        copie.commit()
        self.assertEqual((len(ledger.cours(copie)), len(ledger.executions_actives(copie))), (1, 2))
        self.assertEqual(empreinte(chemin), avant)  # ni table créée ni ligne écrite dans le fichier


if __name__ == "__main__":
    unittest.main()
