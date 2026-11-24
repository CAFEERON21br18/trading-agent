"""
tests/test_pro_import.py — Import du relevé CSV en deux temps (POST /pro/import/apercu puis
/pro/import/confirmer ; dashboard/pro/routes_ecriture.py, import_releve.py, jetons.py).

1. aperçu : compte ce qui serait ajouté, n'écrit rien (grand livre et dossier inchangés), rend un
   jeton ; sans grand livre, rien n'est créé ;
2. confirmation : écrit trades et mouvements ; le jeton ne sert qu'une fois ; réaperçu : rien à
   ajouter, donc pas de jeton ;
3. une erreur dans le fichier : numéro de ligne, pas de jeton, confirmation impossible ;
4. protections : en-tête X-AlphaSignal, POST seulement, 2 Mo au plus, pas de formulaire
   multipart (le fichier n'est jamais écrit sur le disque), texte non UTF-8 refusé ;
5. jeton : usage unique, expiration à 10 minutes, nombre de relevés en attente plafonné.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_import -v
Client de test Flask, grand livre temporaire, relevé inventé ; aucun réseau, rien dans data/.
"""

import io
import os
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from dashboard.pro import import_releve, jetons
from tests.pro_fixtures import empreinte
from tests.pro_page_fixtures import EN_TETE, BasePage
from tests.test_import_mouvements import CSV

CSV_OCTETS = ("﻿" + CSV).encode("utf-8")  # avec la marque d'ordre des octets d'un export
ERREUR = CSV + "pas-une-date,BBB,BUY - MARKET,1,USD 10,USD 10,USD,1\n"


class BaseImport(BasePage):
    def setUp(self):
        super().setUp()
        correctif = mock.patch.object(jetons, "en_attente", jetons.Jetons())
        correctif.start()
        self.addCleanup(correctif.stop)

    def apercu(self, corps=CSV_OCTETS, type_="text/csv", entetes=EN_TETE):
        return self.client.post("/pro/import/apercu", data=corps, content_type=type_, headers=entetes)

    def confirmer(self, jeton, entetes=EN_TETE):
        return self.client.post("/pro/import/confirmer", json={"jeton": jeton}, headers=entetes)

    def lignes(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class TestDeuxTemps(BaseImport):
    def test_apercu_puis_confirmation(self):
        avant, fichiers = empreinte(self.chemin_ledger), sorted(os.listdir(self.dossier.name))
        r = self.apercu()
        self.assertEqual(r.status_code, 200)
        a = r.get_json()
        self.assertEqual({c: a[c] for c in ("trades_a_ajouter", "trades_deja_presents", "mouvements_a_ajouter",
                                            "mouvements_deja_presents", "ignores", "erreurs", "confirmable")},
                         {"trades_a_ajouter": 2, "trades_deja_presents": 0, "mouvements_a_ajouter": 3,
                          "mouvements_deja_presents": 0, "ignores": {"CUSTODY FEE": 1, "STOCK SPLIT": 1},
                          "erreurs": [], "confirmable": True})
        self.assertGreaterEqual(len(a["jeton"]), 40)
        self.assertEqual((empreinte(self.chemin_ledger), sorted(os.listdir(self.dossier.name))), (avant, fichiers))
        self.assertEqual((self.lignes("trades"), len(jetons.en_attente)), (0, 1))  # rien d'écrit, relevé en mémoire

        r = self.confirmer(a["jeton"])
        self.assertEqual(r.status_code, 200)
        c = r.get_json()
        self.assertEqual((c["ecrit"], c["trades_a_ajouter"], c["mouvements_a_ajouter"], c["erreurs"]), (True, 2, 3, []))
        self.assertEqual((self.lignes("trades"), self.lignes("mouvements"), len(jetons.en_attente)), (2, 3, 0))
        self.assertEqual([c.nom for c in ledger.comptes(self.conn)], ["Revolut"])

        self.assertEqual(self.confirmer(a["jeton"]).status_code, 410)  # usage unique
        self.assertEqual(self.lignes("trades"), 2)
        b = self.apercu().get_json()  # même relevé : tout est déjà là
        self.assertEqual((b["trades_a_ajouter"], b["trades_deja_presents"], b["mouvements_deja_presents"],
                          b["confirmable"], b["jeton"]), (0, 2, 3, False, None))

    def test_sans_grand_livre_l_apercu_ne_cree_rien(self):
        absent = self.sans_grand_livre()
        a = self.apercu().get_json()
        self.assertEqual((a["trades_a_ajouter"], a["mouvements_a_ajouter"]), (2, 3))
        self.assertFalse(os.path.exists(os.path.dirname(absent)))
        os.makedirs(os.path.dirname(absent))
        self.assertTrue(self.confirmer(a["jeton"]).get_json()["ecrit"])  # la confirmation, elle, le crée
        lecture = ledger.ouvrir_lecture(absent)
        self.addCleanup(lecture.close)
        self.assertEqual(len(ledger.executions_actives(lecture)), 2)

    def test_erreur_dans_le_fichier_confirmation_impossible(self):
        a = self.apercu(ERREUR.encode("utf-8")).get_json()
        self.assertEqual((a["erreurs"][0][0], a["confirmable"], a["jeton"]), (9, False, None))
        self.assertIn("date illisible", a["erreurs"][0][1])
        self.assertEqual(len(jetons.en_attente), 0)  # un relevé en erreur n'est pas gardé
        for jeton in (None, "", "inconnu", 12):
            with self.subTest(jeton=jeton):
                r = self.confirmer(jeton)
                self.assertEqual((r.status_code, "expiré" in r.get_json()["error"]), (410, True))
        self.assertEqual((self.lignes("trades"), self.lignes("mouvements")), (0, 0))
        # relevé devenu illisible entre l'aperçu et la confirmation : rien n'est écrit non plus
        self.assertEqual(import_releve.confirmer(ERREUR, self.chemin_ledger)["ecrit"], False)
        self.assertEqual(self.lignes("comptes"), 0)


class TestProtections(BaseImport):
    def test_en_tete_et_methode(self):
        for url in ("/pro/import/apercu", "/pro/import/confirmer"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data=CSV_OCTETS, content_type="text/csv").status_code, 403)
                self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual((self.lignes("trades"), len(jetons.en_attente)), (0, 0))

    def test_fichier_refuse(self):
        trop = b"x" * (import_releve.TAILLE_MAX + 1)
        for corps, type_, code, attendu in [(trop, "text/csv", 413, "2 Mo"), (b"", "text/csv", 400, "vide"),
                                            (b"\xff\xfe\x00a", "text/csv", 400, "UTF-8"),
                                            (CSV_OCTETS, "multipart/form-data; boundary=x", 415, "sans formulaire"),
                                            (b"a=1", "application/x-www-form-urlencoded", 415, "sans formulaire")]:
            with self.subTest(type=type_, taille=len(corps)):
                r = self.apercu(corps, type_)
                self.assertEqual(r.status_code, code)
                self.assertIn(attendu, r.get_json()["error"])
        self.assertEqual(len(jetons.en_attente), 0)
        juste = CSV_OCTETS + b"\n" * (import_releve.TAILLE_MAX - len(CSV_OCTETS))  # 2 Mo exactement : accepté
        self.assertEqual(self.apercu(juste).status_code, 200)
        with self.assertRaisesRegex(import_releve.ReleveRefuse, "2 Mo"):
            import_releve.decoder(trop)

    def test_le_fichier_ne_passe_ni_par_un_formulaire_ni_par_le_disque(self):
        with open(os.path.join(RACINE, "dashboard", "pro", "routes_ecriture.py"), encoding="utf-8") as f:
            code = f.read().split('"""', 2)[2]  # hors commentaire d'en-tête
        for interdit in ("request.files", "request.form", "open(", "tempfile", ".save("):
            self.assertNotIn(interdit, code)
        self.assertIn("request.stream.read(import_releve.TAILLE_MAX + 1)", code)

    def test_lecture_en_echec(self):
        with mock.patch.object(import_releve, "apercu", side_effect=RuntimeError("secret")):
            r = self.apercu()
        self.assertEqual((r.status_code, "secret" in r.get_data(as_text=True)), (500, False))
        jeton = self.apercu().get_json()["jeton"]
        with mock.patch.object(import_releve, "confirmer", side_effect=RuntimeError("secret")):
            r = self.confirmer(jeton)
        self.assertEqual((r.status_code, r.get_json()["error"]), (500, "import impossible : rien n'a été écrit"))


class TestJetons(unittest.TestCase):
    def test_usage_unique_expiration_et_plafond(self):
        heure = [1000.0]
        j = jetons.Jetons(horloge=lambda: heure[0])
        a, b = j.deposer("relevé a"), j.deposer("relevé b")
        self.assertNotEqual(a, b)
        self.assertEqual((j.retirer(a), j.retirer(a), j.retirer("inconnu")), ("relevé a", None, None))
        heure[0] += jetons.DUREE_S - 1
        c = j.deposer("relevé c")
        heure[0] += 1  # 10 minutes après le dépôt de b
        self.assertEqual((j.retirer(b), len(j)), (None, 1))
        self.assertEqual(j.retirer(c), "relevé c")
        tous = [j.deposer(f"relevé {n}") for n in range(jetons.MAX_EN_ATTENTE + 2)]
        self.assertEqual(len(j), jetons.MAX_EN_ATTENTE)
        self.assertEqual([j.retirer(t) is None for t in tous], [True, True] + [False] * jetons.MAX_EN_ATTENTE)
        self.assertEqual((jetons.DUREE_S, import_releve.TAILLE_MAX), (600, 2 * 1024 * 1024))

    def test_decoder(self):
        self.assertEqual(import_releve.decoder("﻿Date,Ticker\n".encode("utf-8")), "Date,Ticker\n")
        self.assertEqual(io.StringIO(import_releve.decoder(CSV_OCTETS)).readline(), CSV.splitlines(True)[0])


if __name__ == "__main__":
    unittest.main()
