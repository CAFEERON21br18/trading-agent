"""
tests/test_mouvements.py — Mouvements d'argent du grand livre : dépôts, retraits, dividendes.

1. enregistrer_mouvement : idempotent sur (source, ref_source), valeurs invalides refusées ;
   lecture par compte, dans l'ordre, avec le titre d'un dividende ;
2. la table se crée sur un grand livre déjà existant (ancien schéma, 7 tables) sans rien
   toucher d'autre : mêmes lignes, même schéma, mêmes déclencheurs ;
3. ouverture en lecture seule : None sans fichier, écriture refusée, table absente lue comme vide ;
4. mesures : dividendes, apports nets, bascule de devise, devises mélangées refusées.
L'import du relevé (les trois types qui deviennent des mouvements) : tests/test_import_mouvements.py.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_mouvements -v
Bases dans un dossier temporaire, données inventées ; aucun réseau, aucun .env, rien dans data/.
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
import mesures
from tests import socle_ancien_schema as ancien
from tests.socle_fixtures import BaseLedgerIds, jour, trade


def mouvement(conn, ids, ref, type_="depot", montant="500", j=1, devise="USD", **kw):
    return ledger.enregistrer_mouvement(
        conn, compte_id=ids[0], horodatage=jour(j), type_=type_, montant=montant,
        devise=devise, source="test", ref_source=ref, **kw)


class TestEcritureEtLecture(BaseLedgerIds):
    def test_idempotent_et_relu_dans_l_ordre(self):
        self.assertIsNotNone(mouvement(self.conn, self.ids, "b", "dividende", "1.20", j=6,
                                       instrument_id=self.ids[1]))
        self.assertIsNotNone(mouvement(self.conn, self.ids, "a"))
        self.assertIsNone(mouvement(self.conn, self.ids, "a", "retrait", "999"))  # même référence
        depot, dividende = ledger.mouvements(self.conn, self.ids[0])
        self.assertEqual((depot.type, depot.montant, depot.devise, depot.symbole, depot.horodatage),
                         ("depot", D("500"), "USD", None, jour(1)))
        self.assertEqual((dividende.type, dividende.montant, dividende.symbole),
                         ("dividende", D("1.20"), "AAA"))

    def test_valeurs_invalides_refusees(self):
        for kw in ({"type_": "virement"}, {"montant": "0"}, {"montant": "-5"}, {"montant": "abc"}):
            with self.subTest(**kw), self.assertRaises(ledger.EcritureInvalide):
                mouvement(self.conn, self.ids, "x", **kw)
        self.assertEqual(ledger.mouvements(self.conn, self.ids[0]), [])

    def test_filtre_par_compte(self):
        mouvement(self.conn, self.ids, "a")
        autre = ledger.compte(self.conn, "Autre", "reel", "EUR")
        self.assertEqual(ledger.mouvements(self.conn, autre), [])
        self.assertEqual(len(ledger.mouvements(self.conn, self.ids[0])), 1)
        self.assertEqual([(c.nom, c.type, c.devise) for c in ledger.comptes(self.conn)],
                         [("Test", "paper", "USD"), ("Autre", "reel", "EUR")])


def etat(conn) -> tuple:
    """Schéma et contenu de tout ce qui n'est pas la table mouvements."""
    schema = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"
                          " WHERE tbl_name != 'mouvements' ORDER BY name").fetchall()
    lignes = {t: [tuple(l) for l in conn.execute(f"SELECT * FROM {t} ORDER BY id")] for t in ancien.TABLES}
    return [tuple(l) for l in schema], lignes


class TestBaseExistante(BaseLedgerIds):
    def ancienne_base(self) -> str:
        chemin = os.path.join(self.dossier.name, "ancien.db")
        conn = ancien.creer_ancien(chemin)
        ids = (ledger.compte(conn, "Paper agent", "paper", "EUR"), ledger.instrument(conn, "AAA", "USD"))
        trade(conn, ids, "a", couts=[("commission", "1")], contexte={"bras": "regles", "stop_initial": "95"})
        trade(conn, ids, "b", sens="vente", prix="110", j=3)
        ledger.enregistrer_taux(conn, date(2030, 1, 3), "1.10", "test")
        ledger.enregistrer_valeur(conn, ids[0], date(2030, 1, 3), "1000", "EUR")
        conn.commit()
        conn.close()
        return chemin

    def test_la_table_se_cree_sans_rien_toucher_d_autre(self):
        chemin = self.ancienne_base()
        brut = sqlite3.connect(chemin)
        self.addCleanup(brut.close)
        avant = etat(brut)
        self.assertEqual(brut.execute("SELECT COUNT(*) FROM sqlite_master WHERE tbl_name = 'mouvements'")
                         .fetchone()[0], 0)
        conn = ledger.ouvrir(chemin)
        self.addCleanup(conn.close)
        self.assertEqual(etat(brut), avant)  # mêmes tables, index, déclencheurs et lignes
        self.assertEqual(len(avant[1]["trades"]), 2)
        noms = {l[0] for l in brut.execute("SELECT name FROM sqlite_master WHERE tbl_name = 'mouvements'")}
        self.assertLessEqual({"mouvements", "mouvements_sans_modif", "mouvements_sans_suppr",
                              "idx_mouvements_compte"}, noms)
        compte_id = ledger.comptes(conn)[0].id
        mouvement(conn, (compte_id, None), "m")
        for requete in ("UPDATE mouvements SET montant = '1'", "DELETE FROM mouvements"):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "ecriture seule"):
                conn.execute(requete)
        conn.commit()
        self.assertEqual(len(ledger.executions_actives(conn)), 2)  # l'ancien contenu se lit toujours
        ledger.ouvrir(chemin).close()  # une seconde ouverture ne change rien non plus
        self.assertEqual(etat(brut), avant)

    def test_lecture_seule(self):
        self.assertIsNone(ledger.ouvrir_lecture(os.path.join(self.dossier.name, "absent.db")))
        self.assertFalse(os.path.exists(os.path.join(self.dossier.name, "absent.db")))  # rien de créé
        chemin = self.ancienne_base()
        conn = ledger.ouvrir_lecture(chemin)
        self.addCleanup(conn.close)
        compte_id = ledger.comptes(conn)[0].id
        self.assertEqual(ledger.mouvements(conn, compte_id), [])  # table absente : lue comme vide
        self.assertEqual(ledger.references_presentes(conn, "mouvements", "test"), set())
        self.assertEqual(ledger.references_presentes(conn, "trades", "test"), {"a", "b"})
        with self.assertRaises(ValueError):
            ledger.references_presentes(conn, "comptes", "test")
        with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
            conn.execute("INSERT INTO comptes (nom, type, devise, cree_le) VALUES ('x', 'demo', 'EUR', 'x')")


class TestMesures(BaseLedgerIds):
    def setUp(self):
        super().setUp()
        mouvement(self.conn, self.ids, "d1", "depot", "500", j=2)
        mouvement(self.conn, self.ids, "d2", "depot", "250", j=4)
        mouvement(self.conn, self.ids, "r1", "retrait", "100", j=5)
        mouvement(self.conn, self.ids, "v1", "dividende", "1.20", j=6)
        mouvement(self.conn, self.ids, "v2", "dividende", "0.30", j=8)
        self.mouvements = ledger.mouvements(self.conn, self.ids[0])

    def test_dividendes_et_apports_nets(self):
        d = mesures.dividendes(self.mouvements)
        self.assertEqual((d.nom, d.valeur, d.n, d.debut, d.fin, d.decidable, d.raison),
                         ("dividendes", 1.5, 2, date(2030, 1, 6), date(2030, 1, 8), True, ""))
        a = mesures.apports_nets(self.mouvements)
        self.assertEqual((a.nom, a.valeur, a.n, a.debut, a.fin, a.decidable),
                         ("apports nets", 650.0, 3, date(2030, 1, 2), date(2030, 1, 5), True))

    def test_sans_mouvement_non_calculable(self):
        for f in (mesures.dividendes, mesures.apports_nets):
            m = f([])
            self.assertEqual((m.valeur, m.n, m.decidable, m.raison), (None, 0, False, "non calculable"))
        seulement_dividendes = [m for m in self.mouvements if m.type == "dividende"]
        self.assertIsNone(mesures.apports_nets(seulement_dividendes).valeur)  # jamais 0

    def test_bascule_de_devise_et_devises_melangees(self):
        mouvement(self.conn, self.ids, "e1", "depot", "100", j=4, devise="EUR")
        melanges = ledger.mouvements(self.conn, self.ids[0])
        with self.assertRaisesRegex(ValueError, "devises mélangées"):
            mesures.apports_nets(melanges)
        taux = {date(2030, 1, d): D("1.25") for d in range(1, 9)}
        en_euros = mesures.mouvements_en_devise(melanges, "EUR", taux)
        self.assertEqual({m.devise for m in en_euros}, {"EUR"})
        self.assertEqual(mesures.apports_nets(en_euros).valeur, 620.0)  # (500 + 250 − 100) / 1,25 + 100
        with self.assertRaises(mesures.TauxManquant):
            mesures.mouvements_en_devise(melanges, "EUR", {})


if __name__ == "__main__":
    unittest.main()
