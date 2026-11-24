"""
tests/socle_paper_fixtures.py — Base paper fabriquée pour les tests de l'adaptateur paper du socle
(importeurs/paper.py, scripts/ledger_sync_paper.py).

La table positions est créée par le code du paper trader lui-même (initialiser_paper_db, mode WAL),
puis la colonne « boucle » est ajoutée comme le fait scripts/marquer_boucles.py : si le schéma de
l'agent change, ces tests le voient. Positions entièrement inventées ; dossier temporaire, jamais
data/ ; aucun réseau, aucun .env.
"""

import os
import sqlite3
from unittest import mock

from tests.socle_fixtures import BaseLedger
from utils import database
from utils.portfolio_db import initialiser_paper_db

ENTREE = "2030-01-02T10:00:00+00:00"
SORTIE = "2030-01-03T15:30:00+00:00"


def creer_base(chemin: str, boucle: bool = True) -> None:
    """Base de l'agent neuve, avec ou sans la colonne de marquage des positions « boucle »."""
    with mock.patch.object(database, "DB_PATH", chemin):
        initialiser_paper_db()
    if boucle:
        executer(chemin, "ALTER TABLE positions ADD COLUMN boucle INTEGER DEFAULT 0")


def executer(chemin: str, sql: str, params=()) -> int:
    conn = sqlite3.connect(chemin)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def position(chemin: str, ticker="AAA", direction="LONG", statut="CLOSED_TP", prix=100.0, sortie=110.0,
             quantite=2.0, stop=95.0, type_actif="action", entree_le=ENTREE, sortie_le=SORTIE, boucle=0) -> int:
    """Insère une position inventée et rend son identifiant."""
    ouverte = statut == "OPEN"
    return executer(
        chemin,
        "INSERT INTO positions (ticker, asset_type, direction, status, entry_price, entry_date, quantity,"
        " invested_amount, stop_loss, target_1, exit_price, exit_date, boucle)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker, type_actif, direction, statut, prix, entree_le, quantite, prix * quantite, stop, prix * 1.1,
         None if ouverte else sortie, None if ouverte else sortie_le, boucle))


def fermer(chemin: str, pos_id: int, sortie: float, sortie_le: str = SORTIE) -> None:
    executer(chemin, "UPDATE positions SET status = 'CLOSED_SL', exit_price = ?, exit_date = ? WHERE id = ?",
             (sortie, sortie_le, pos_id))


class BasePaperLedger(BaseLedger):
    """Un grand livre neuf (self.conn) et une base paper neuve (self.base) par test."""

    def setUp(self):
        super().setUp()
        self.base = os.path.join(self.dossier.name, "database.db")
        creer_base(self.base)

    def nb_trades(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
