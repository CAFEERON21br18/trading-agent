"""
tests/test_jev_fantome_isolation.py — Fantôme Jev (REGISTRE_CRITERES §8.1) : le paper
actuel et ses tables sont strictement identiques avec et sans le fantôme ; le fantôme
ne lit aucune table du paper ; aucun autre module ne lit les tables du fantôme.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_fantome_isolation -v
Bases SQLite temporaires, valeurs inventées, aucun réseau.
"""

import os
import re
import sqlite3
import unittest
from unittest import mock

from tests.jev_fantome_fixtures import RACINE, BaseFantome, observation  # en premier : variables de config.py
from utils import database, jev_paper_db
from agents.jev import fantome

TABLES_PAPER = ("positions", "transactions", "portfolio_snapshots")
JOURS = ("2026-11-02", "2026-11-03", "2026-11-09", "2026-11-10")


def _paper_fictif() -> None:
    """Positions paper inventées (une ouverte, une fermée) et un snapshot, dans la base courante."""
    from utils import portfolio_db as pdb
    pdb.initialiser_paper_db()
    base = {"asset_type": "etf", "direction": "LONG", "entry_price": 100.0, "quantity": 0.5,
            "invested_amount": 50.0, "stop_loss": 95.0, "target_1": 110.0, "confidence": 8}
    pdb.creer_position({**base, "ticker": "QQQ", "entry_date": "2026-10-20T07:30:00+00:00"})
    ferme = pdb.creer_position({**base, "ticker": "VOO", "entry_date": "2026-10-21T07:30:00+00:00"})
    pdb.fermer_position(ferme, 104.0, "test", "CLOSED_TP")
    pdb.enregistrer_snapshot({"date": "2026-10-30", "cash": 950.0, "invested": 50.0, "unrealized_pnl": 1.0,
                              "total_value": 1001.0, "open_positions_count": 1})


def _contenu(chemin: str) -> dict:
    """Schéma et lignes de toutes les tables hors fantôme (compteurs AUTOINCREMENT compris)."""
    conn = sqlite3.connect(chemin)
    try:
        noms = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                           "AND name NOT LIKE 'jev_paper_%' ORDER BY name")]
        out = {n: conn.execute(f"SELECT * FROM {n} WHERE name NOT LIKE 'jev_paper_%' ORDER BY name"
                               if n == "sqlite_sequence"
                               else f"SELECT * FROM {n} ORDER BY rowid").fetchall() for n in noms}
        out["schema"] = conn.execute("SELECT type, name, sql FROM sqlite_master "
                                     "WHERE name NOT LIKE '%jev_paper_%' ORDER BY name").fetchall()
        return out
    finally:
        conn.close()


def _lectures_paper() -> dict:
    """Ce que lisent le Paper Trader, le Budget Manager et l'observation Jev du lendemain."""
    from utils.portfolio_db import lire_positions_ouvertes
    from agents.paper_trader.portfolio import etat_portefeuille
    from agents.budget_manager.manager import _cash_disponible_actuel
    from agents.budget_manager.strategy import detecter_mode
    from agents.jev.observer import _contexte_paper
    return {"ouvertes": lire_positions_ouvertes(), "mode": detecter_mode(), "contexte_jev": _contexte_paper(),
            "cash_bm": _cash_disponible_actuel("NORMAL"),
            "etat": etat_portefeuille(prix_courants={}, with_live_prices=False)}


class TestPaperIdentique(BaseFantome):

    def _copie(self, nom: str) -> str:
        """Copie exacte de la base de départ (API de sauvegarde SQLite)."""
        chemin = os.path.join(self.dossier.name, nom)
        src, dst = sqlite3.connect(self.chemin), sqlite3.connect(chemin)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        return chemin

    def _lancer_sur(self, chemin: str, avec_fantome: bool) -> tuple[dict, dict]:
        with mock.patch.object(database, "DB_PATH", chemin):
            if avec_fantome:
                for jour in JOURS:
                    self.assertIsNotNone(fantome.executer("quotidien", jour))
                self.assertGreaterEqual(len(self.positions()), 3)  # le fantôme a bien acheté et vendu
            return _contenu(chemin), _lectures_paper()

    def test_tables_et_lectures_du_paper_identiques(self):
        _paper_fictif()
        self.ajouter_obs(observation("SPY", JOURS[0]), observation("QQQ", JOURS[1], position_ouverte=1),
                         observation("NVDA", JOURS[1], p_acheter=0.9), observation("SPY", JOURS[2]))
        self.ajouter_barres("SPY", {f"2026-11-{j:02d}": 100.0 + j for j in (2, 3, 4, 5, 6, 9)})
        sans_contenu, sans_lectures = self._lancer_sur(self._copie("sans.db"), False)
        avec_contenu, avec_lectures = self._lancer_sur(self._copie("avec.db"), True)
        for table in (*TABLES_PAPER, "sqlite_sequence", "schema"):
            self.assertEqual(avec_contenu[table], sans_contenu[table], table)
        self.assertEqual(avec_contenu, sans_contenu)
        self.assertEqual(avec_lectures, sans_lectures)


class TestLecturesDuFantome(BaseFantome):

    def test_aucune_table_du_paper_lue_ni_ecrite(self):
        touchees = set()

        def autorisation(action, a1, a2, base, source):
            if action in (sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                          sqlite3.SQLITE_DELETE):
                touchees.add(a1)
            return sqlite3.SQLITE_OK

        connexion_d_origine = jev_paper_db.get_connection

        def connexion_surveillee():
            conn = connexion_d_origine()
            conn.set_authorizer(autorisation)
            return conn

        _paper_fictif()
        self.ajouter_obs(observation("SPY", JOURS[0]), observation("NVDA", JOURS[2]))
        self.ajouter_barres("SPY", {f"2026-11-{j:02d}": 101.0 for j in (2, 3, 4, 5, 6)})
        with mock.patch.object(jev_paper_db, "get_connection", connexion_surveillee):
            for jour in JOURS:
                self.assertIsNotNone(fantome.executer("quotidien", jour))
        self.assertIn("jev_paper_positions", touchees)
        self.assertLessEqual(touchees, {"jev_observations", "prices", "jev_paper_positions",
                                        "jev_paper_journal", "sqlite_master", "sqlite_sequence"})

    def test_seul_le_fantome_lit_ses_tables(self):
        autorises = {os.path.join("utils", "jev_paper_db.py"), os.path.join("agents", "jev", "fantome.py")}
        trouves = set()
        for dossier, sous, fichiers in os.walk(RACINE):
            sous[:] = [d for d in sous if d not in (".git", ".venv", "venv", "__pycache__", "tests")]
            for f in fichiers:
                if f.endswith(".py"):
                    chemin = os.path.join(dossier, f)
                    with open(chemin, encoding="utf-8", errors="ignore") as fh:
                        if re.search(r"jev_paper", fh.read()):
                            trouves.add(os.path.relpath(chemin, RACINE))
        self.assertEqual(trouves, autorises)


class TestBranchement(BaseFantome):

    def test_hors_cycle_quotidien_rien(self):
        self.ajouter_obs(observation("SPY", JOURS[0]))
        for cycle in ("manuel", "tactical", "strategique"):
            self.assertIsNone(fantome.executer(cycle, JOURS[0]))
        conn = sqlite3.connect(database.DB_PATH)
        try:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'jev_paper_%'").fetchone())
        finally:
            conn.close()

    def test_une_erreur_ne_remonte_jamais_au_cycle(self):
        with mock.patch.object(fantome, "traiter", side_effect=RuntimeError("panne")):
            self.assertIsNone(fantome.executer("quotidien", JOURS[0]))

    def test_appele_apres_l_observation_dans_le_cycle_quotidien(self):
        with open(os.path.join(RACINE, "agents", "orchestrator.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertLess(source.index("observer_jev(jev_lot)"), source.index("executer_fantome_jev(cycle_registre)"))


if __name__ == "__main__":
    unittest.main()
