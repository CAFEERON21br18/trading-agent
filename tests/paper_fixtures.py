"""
tests/paper_fixtures.py — Base temporaire et décisions inventées pour les tests du Paper Trader
(mécanisme d'entrée v2, anti-boucle, positions « boucle »). Aucun réseau, aucun LLM, aucun email.
"""

import math
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

from utils import database
from utils.portfolio_db import initialiser_paper_db


def decision(ticker="AAA", action="BUY", conf=9, prix=117.0):
    return {"ticker": ticker,
            "decision": {"ticker": ticker, "decision": action, "confidence": conf, "score_composite": 2.4,
                         "reasoning": f"Thèse inventée {ticker}", "style": "normal", "taille_factor": 1.0,
                         "convergences": ["technique+sentiment"], "contradictions": []},
            "analyses": {"technique": {"direction": "ACHAT", "confiance": 7, "prix": prix},
                         "risque": {"valide": True, "signal": {"montant_investi": 50.0}}, "memory": {}}}


def inserer_position(ticker, prix, statut="CLOSED_SL", entree="2026-10-01T10:00:00+00:00",
                     sortie="2026-10-01T10:05:00+00:00", pnl=-1.0, direction="LONG"):
    conn = database.get_connection()
    conn.execute("INSERT INTO positions (ticker, asset_type, direction, status, entry_price, entry_date, quantity, "
                 "invested_amount, stop_loss, target_1, exit_price, exit_date, pnl_euros, pnl_percent) "
                 "VALUES (?, 'action', ?, ?, ?, ?, 1, 10, ?, ?, ?, ?, ?, ?)",
                 (ticker, direction, statut, prix, entree, prix * 0.97, prix * 1.06,
                  None if statut == "OPEN" else prix + pnl, None if statut == "OPEN" else sortie, pnl, pnl * 10))
    conn.commit()
    conn.close()


class BasePaper(unittest.TestCase):
    """Base SQLite temporaire avec 400 barres 1d inventées pour AAA ; pièges réseau, LLM et email."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.chemin = os.path.join(self.dossier.name, "t.db")
        self.patchs = [mock.patch.object(database, "DB_PATH", self.chemin),
                       mock.patch("agents.paper_trader.executor._email_ouverture"),
                       mock.patch("agents.paper_trader.executor._email_fermeture"),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")),
                       mock.patch("utils.llm.ask_llm", side_effect=AssertionError("aucun LLM"))]
        for p in self.patchs:
            p.start()
        database.initialiser_base()
        initialiser_paper_db()
        conn = database.get_connection()
        for i in range(400):
            c = 100 + 10 * math.sin(i / 15) + i * 0.05  # cours inventés
            conn.execute("INSERT INTO prices (ticker, timeframe, timestamp, open, high, low, close, volume) "
                         "VALUES ('AAA', '1d', ?, ?, ?, ?, ?, 1000)",
                         ((date(2025, 1, 1) + timedelta(days=i)).isoformat(), c, c + 1, c - 1, c))
        conn.commit()
        conn.close()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def positions(self) -> list[dict]:
        conn = database.get_connection()
        rows = [dict(r) for r in conn.execute("SELECT * FROM positions ORDER BY id")]
        conn.close()
        return rows
