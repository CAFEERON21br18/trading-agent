"""
tests/jev_fantome_fixtures.py — Base temporaire des tests du fantôme Jev
(REGISTRE_CRITERES §8) : observations, barres journalières, positions paper.
Toutes les valeurs sont inventées. Aucun réseau.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

import config
from utils import database, jev_db, jev_paper_db
from agents.jev import fantome

PRICES_DDL = "CREATE TABLE IF NOT EXISTS prices (ticker TEXT, timeframe TEXT, timestamp TEXT, close REAL)"


def state(direction: str | None = "LONG") -> str:
    """State minimal : seule la direction du signal du Risk Manager est lue par le fantôme."""
    signal = {"direction": direction, "montant_investi": 40.0} if direction else {}
    return json.dumps({"ticker": "X", "risque": {"valide": True, "signal": signal}})


def observation(ticker: str, jour: str, p_acheter: float = 0.8, **autres) -> dict:
    ligne = {"horodatage": f"{jour}T06:31:00+00:00", "jour": jour, "ticker": ticker,
             "cycle": "quotidien", "statut": "ok", "questions_version": "v1", "modele": "jev-1.13.0",
             "position_ouverte": 0, "prix": 100.0, "p_acheter": p_acheter, "conviction_niveau": 3,
             "montant_risque": 40.0, "mode_bm": "NORMAL", "state": state(),
             "decision_moteur": "HOLD", "regime_jev": "range", "regime_moteur": "range"}
    ligne.update(autres)
    return ligne


class BaseFantome(unittest.TestCase):
    """Base SQLite temporaire (database.DB_PATH détourné), CAPITAL 1000 €, 20 positions max."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.chemin = os.path.join(self.dossier.name, "t.db")
        self.patchs = [mock.patch.object(database, "DB_PATH", self.chemin),
                       mock.patch.object(config, "CAPITAL", 1000.0),
                       mock.patch.object(config, "MAX_POSITIONS_SIMULTANEES", 20)]
        for p in self.patchs:
            p.start()
        self.preparer_base(self.chemin)

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    @staticmethod
    def preparer_base(chemin: str) -> None:
        conn = sqlite3.connect(chemin)
        for ddl in (*jev_db._DDL, PRICES_DDL):
            conn.execute(ddl)
        conn.commit()
        conn.close()

    def ajouter_obs(self, *observations: dict) -> None:
        conn = sqlite3.connect(database.DB_PATH)
        for o in observations:
            cols = [c for c in jev_db.COLONNES if c in o]
            conn.execute(f"INSERT INTO jev_observations ({', '.join(cols)}) "
                         f"VALUES ({', '.join('?' * len(cols))})", [o[c] for c in cols])
        conn.commit()
        conn.close()

    def ajouter_barres(self, ticker: str, barres: dict) -> None:
        """barres : {jour AAAA-MM-JJ: clôture}."""
        conn = sqlite3.connect(database.DB_PATH)
        conn.executemany("INSERT INTO prices VALUES (?, '1d', ?, ?)",
                         [(ticker, f"{j} 00:00:00", c) for j, c in barres.items()])
        conn.commit()
        conn.close()

    def lancer(self, jour: str) -> dict:
        """traiter() directement : une erreur fait échouer le test au lieu d'être journalisée."""
        conn = jev_paper_db.connexion()
        try:
            return fantome.traiter(conn, jour)
        finally:
            conn.close()

    def lire(self, table: str) -> list[dict]:
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        finally:
            conn.close()

    def positions(self) -> list[dict]:
        return self.lire("jev_paper_positions")

    def refus(self) -> dict:
        """{ticker: motif} des observations non achetées."""
        return {l["ticker"]: l["motif"] for l in self.lire("jev_paper_journal") if l["evenement"] == "refus"}
