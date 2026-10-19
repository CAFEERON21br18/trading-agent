"""
tests/test_boucles_stats.py — Positions « boucle » (REGISTRE_CRITERES v1.8, §9.2 et §9.5).

1. scripts/marquer_boucles.py : à blanc, rien n'est écrit (fichier identique) ; --appliquer sauvegarde
   d'abord, ajoute la colonne et marque exactement la définition (même ticker, même entry_price exact,
   au moins 3 positions) ; relancé, il ne fait rien ;
2. EXCLURE_BOUCLES_STATS à 0 : résultats identiques à aujourd'hui (positions fermées, mode du Budget
   Manager, leçons et patterns) ; à 1 : positions « boucle » exclues ; à 1 sans colonne : identiques ;
3. nombre_marquees (empreinte des paramètres du registre) : lecture seule, None sans base ni colonne.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_boucles_stats -v
Base temporaire, données inventées ; aucun réseau, aucun LLM, aucun email.
"""

import contextlib
import hashlib
import io
import os
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import config
from utils import database, portfolio_db, positions_boucles, registre
from agents.budget_manager import strategy
from agents.trade_journalist import learner
from scripts import marquer_boucles
from tests.paper_fixtures import BasePaper, inserer_position


def empreinte(chemin):
    with open(chemin, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class BaseBoucles(BasePaper):
    """10 positions fermées : AAA à 10.0 ×3 et CCC à 5.5 ×4 (boucles), AAA à 11.0 ×2 et BBB à 10.0 (non)."""

    def setUp(self):
        super().setUp()
        h = iter(range(10, 60))
        lignes = [("AAA", 10.0, -1.0)] * 3 + [("CCC", 5.5, 2.0)] * 4 + [("AAA", 11.0, 3.0)] * 2 + [("BBB", 10.0, 1.0)]
        for t, p, pnl in lignes:
            m = next(h)
            inserer_position(t, p, "CLOSED_SL" if pnl < 0 else "CLOSED_TP", entree=f"2026-10-01T10:{m}:00+00:00",
                             sortie=f"2026-10-01T11:{m}:00+00:00", pnl=pnl)
        self.attendus = {r["id"] for r in self.positions() if (r["ticker"], r["entry_price"]) in
                         {("AAA", 10.0), ("CCC", 5.5)}}
        self.sauvegardes = os.path.join(self.dossier.name, "sauvegardes")

    def marquer(self, appliquer):
        with contextlib.redirect_stdout(io.StringIO()):
            return marquer_boucles.marquer(self.chemin, appliquer, self.sauvegardes)


class TestMarquage(BaseBoucles):
    def test_a_blanc_rien_n_est_ecrit(self):
        avant = empreinte(self.chemin)
        r = self.marquer(False)
        self.assertEqual((r["action"], r["a_marquer"], r["positions"]), ("à blanc", 7, 10))
        self.assertEqual(sorted(r["series"]), [("AAA", 3), ("CCC", 4)])
        self.assertEqual(empreinte(self.chemin), avant)
        self.assertFalse(os.path.exists(self.sauvegardes))
        self.assertNotIn("boucle", self.positions()[0])

    def test_appliquer_puis_relancer(self):
        r = self.marquer(True)
        self.assertEqual((r["action"], r["controle_ok"]), ("appliquée", True))
        self.assertTrue(os.path.isfile(r["sauvegarde"]))
        self.assertEqual({p["id"] for p in self.positions() if p["boucle"] == 1}, self.attendus)
        self.assertEqual({p["boucle"] for p in self.positions() if p["id"] not in self.attendus}, {0})
        r2 = self.marquer(True)
        self.assertEqual(r2["action"], "aucune")
        # pas de seconde sauvegarde (la copie, en mode WAL comme la base, a ses fichiers -wal et -shm)
        self.assertEqual(len([f for f in os.listdir(self.sauvegardes) if f.endswith(".db")]), 1)

    def test_main_a_blanc(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = marquer_boucles.main(["--base", self.chemin, "--sauvegardes", self.sauvegardes])
        self.assertEqual(code, 0)
        self.assertIn("marquerait 7 position(s) « boucle » sur 10 (2 série(s))", sortie.getvalue())


class TestInterrupteur(BaseBoucles):
    def test_a_zero_resultats_identiques(self):
        sans_colonne = positions_boucles.fermees_recentes(20)
        self.marquer(True)
        self.assertEqual([p["id"] for p in positions_boucles.fermees_recentes(20)], [p["id"] for p in sans_colonne])
        self.assertEqual(positions_boucles.fermees_recentes(20), portfolio_db.lire_positions_recentes_fermees(20))

    def test_a_un_boucles_exclues(self):
        self.marquer(True)
        with mock.patch.object(config, "EXCLURE_BOUCLES_STATS", 1):
            ids = {p["id"] for p in positions_boucles.fermees_recentes(20)}
        self.assertEqual(len(ids), 3)
        self.assertFalse(ids & self.attendus)

    def test_a_un_sans_colonne_identique(self):
        with mock.patch.object(config, "EXCLURE_BOUCLES_STATS", 1):
            self.assertEqual(positions_boucles.fermees_recentes(20), portfolio_db.lire_positions_recentes_fermees(20))

    def test_mode_du_budget_manager(self):
        # les 3 fermetures les plus récentes sont des pertes en boucle (AAA à 10.0)
        conn = database.get_connection()
        conn.execute("UPDATE positions SET exit_date = '2026-10-02T09:00:00+00:00' WHERE ticker = 'AAA' AND entry_price = 10.0")
        conn.commit()
        conn.close()
        self.marquer(True)
        self.assertEqual(strategy.detecter_mode(), "DEFENSIF")
        with mock.patch.object(config, "EXCLURE_BOUCLES_STATS", 1):
            self.assertEqual(strategy.detecter_mode(), "NORMAL")

    def test_lecons_et_patterns(self):
        self.marquer(True)
        for valeur, attendu in ((0, True), (1, False)):
            lecons, patterns = (os.path.join(self.dossier.name, f"{n}{valeur}.md") for n in ("lecons", "patterns"))
            with mock.patch.object(config, "EXCLURE_BOUCLES_STATS", valeur), \
                    mock.patch.object(learner, "LESSONS_MD", lecons), mock.patch.object(learner, "PATTERNS_MD", patterns):
                learner.auto_apprendre()
            texte = open(lecons, encoding="utf-8").read() if os.path.exists(lecons) else ""
            motifs = open(patterns, encoding="utf-8").read() if os.path.exists(patterns) else ""
            self.assertEqual("LECON-PERTES-AAA" in texte, attendu, valeur)
            self.assertEqual("PATTERN-CCC-LONG" in motifs, attendu, valeur)


class TestEmpreinte(BaseBoucles):
    def test_nombre_marquees_et_parametres(self):
        self.assertIsNone(positions_boucles.nombre_marquees())  # colonne absente
        self.marquer(True)
        self.assertEqual(positions_boucles.nombre_marquees(), 7)
        p = registre.parametres_actifs()
        self.assertEqual((p["EXCLURE_BOUCLES_STATS"], p["BOUCLES_MARQUEES"], p["MECANISME_ENTREE"]), (0, 7, 2))
        absent = os.path.join(self.dossier.name, "absent.db")
        with mock.patch.object(database, "DB_PATH", absent):
            self.assertIsNone(positions_boucles.nombre_marquees())
        self.assertFalse(os.path.exists(absent))  # jamais de base créée


if __name__ == "__main__":
    unittest.main()
