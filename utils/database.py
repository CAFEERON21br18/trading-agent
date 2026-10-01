"""
utils/database.py — Connexion SQLite et helpers de base de données
Crée automatiquement les tables au premier démarrage.
"""

import sqlite3
import os
from datetime import datetime
from utils.logger import get_logger
from utils.audit_trace import tracer_sql

logger = get_logger(__name__)

# Chemin vers la base de données
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "data", "database.db")


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec le mode WAL pour la concurrence."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row  # Accès par nom de colonne
    tracer_sql(conn)  # audit du chat (Phase 4) : no-op hors requête auditée
    return conn


def initialiser_base():
    """Crée toutes les tables si elles n'existent pas encore."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Table : prix OHLCV
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                timeframe   TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                volume      REAL,
                created_at  TEXT    DEFAULT (datetime('now')),
                UNIQUE(ticker, timeframe, timestamp)
            )
        """)

        # Table : indicateurs techniques calculés
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicators (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                timeframe   TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                rsi         REAL,
                macd        REAL,
                macd_signal REAL,
                macd_hist   REAL,
                bb_upper    REAL,
                bb_middle   REAL,
                bb_lower    REAL,
                ema_20      REAL,
                ema_50      REAL,
                ema_200     REAL,
                atr         REAL,
                adx         REAL,
                created_at  TEXT    DEFAULT (datetime('now')),
                UNIQUE(ticker, timeframe, timestamp)
            )
        """)

        # Table : signaux émis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id       TEXT    UNIQUE NOT NULL,
                ticker          TEXT    NOT NULL,
                direction       TEXT    NOT NULL,
                timeframe       TEXT,
                confidence      INTEGER,
                price_at_signal REAL,
                stop_loss       REAL,
                target_1        REAL,
                target_2        REAL,
                source_agents   TEXT,
                reason          TEXT,
                timestamp       TEXT    NOT NULL,
                created_at      TEXT    DEFAULT (datetime('now'))
            )
        """)

        # Table : résultats des signaux (mis à jour après clôture)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id       TEXT    UNIQUE NOT NULL,
                exit_price      REAL,
                pnl_pct         REAL,
                duration        TEXT,
                correct         TEXT,
                lesson          TEXT,
                closed_at       TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
            )
        """)

        # Table : données de sentiment (Fear & Greed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sentiment (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL UNIQUE,
                fear_greed_crypto  INTEGER,
                fear_greed_label   TEXT,
                created_at      TEXT    DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Base de données initialisée avec succès.")

    except Exception as e:
        logger.error(f"Erreur initialisation base de données : {e}")
        raise


def sauvegarder_prix(ticker: str, timeframe: str, df) -> int:
    """
    Sauvegarde un DataFrame OHLCV dans la table prices.
    Ignore les doublons (UNIQUE sur ticker + timeframe + timestamp).
    Retourne le nombre de lignes insérées.
    """
    lignes_inserees = 0
    try:
        conn = get_connection()
        cursor = conn.cursor()

        for timestamp, row in df.iterrows():
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO prices
                        (ticker, timeframe, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticker,
                    timeframe,
                    str(timestamp),
                    float(row.get("Open",  0) or 0),
                    float(row.get("High",  0) or 0),
                    float(row.get("Low",   0) or 0),
                    float(row.get("Close", 0) or 0),
                    float(row.get("Volume",0) or 0),
                ))
                lignes_inserees += cursor.rowcount
            except Exception as e:
                logger.warning(f"Ligne ignorée ({ticker} {timestamp}) : {e}")

        conn.commit()
        conn.close()
        logger.info(f"{ticker} [{timeframe}] : {lignes_inserees} nouvelles lignes sauvegardées.")

    except Exception as e:
        logger.error(f"Erreur sauvegarde prix {ticker} : {e}")

    return lignes_inserees


def lire_prix(ticker: str, timeframe: str, limite: int = 200):
    """
    Lit les N dernières bougies OHLCV pour un actif/timeframe.
    Retourne une liste de sqlite3.Row.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM prices
            WHERE ticker = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (ticker, timeframe, limite))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Erreur lecture prix {ticker} [{timeframe}] : {e}")
        return []
