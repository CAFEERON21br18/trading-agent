"""
utils/portfolio_db.py — Schéma & accès BDD pour le Paper Trading Engine
Tables : positions, transactions, portfolio_snapshots.
Toutes les opérations sont 100% paper trading — aucun ordre réel.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialiser_paper_db() -> None:
    """Crée les 3 tables paper trading si elles n'existent pas."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT NOT NULL,
                asset_type      TEXT,
                direction       TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'OPEN',
                entry_price     REAL NOT NULL,
                entry_date      TEXT NOT NULL,
                quantity        REAL NOT NULL,
                invested_amount REAL NOT NULL,
                stop_loss       REAL NOT NULL,
                target_1        REAL NOT NULL,
                target_2        REAL,
                exit_price      REAL,
                exit_date       TEXT,
                pnl_euros       REAL,
                pnl_percent     REAL,
                confidence      INTEGER,
                entry_reason    TEXT,
                exit_reason     TEXT,
                signals_used    TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                type        TEXT NOT NULL,
                ticker      TEXT NOT NULL,
                price       REAL NOT NULL,
                quantity    REAL NOT NULL,
                amount      REAL NOT NULL,
                date        TEXT NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                date                      TEXT NOT NULL,
                cash                      REAL NOT NULL,
                invested                  REAL NOT NULL,
                unrealized_pnl            REAL NOT NULL,
                total_value               REAL NOT NULL,
                daily_return_percent      REAL,
                cumulative_return_percent REAL,
                open_positions_count      INTEGER,
                created_at                TEXT DEFAULT (datetime('now'))
            )
        """)
        # v5.5.1 — Trailing stop intelligent (Skill technique 2)
        try: c.execute("ALTER TABLE positions ADD COLUMN trailing_stop_active INTEGER DEFAULT 0")
        except Exception: pass
        try: c.execute("ALTER TABLE positions ADD COLUMN trailing_stop_price REAL")
        except Exception: pass
        try: c.execute("ALTER TABLE positions ADD COLUMN atr_multiplier REAL DEFAULT 2.0")
        except Exception: pass
        conn.commit()
        conn.close()
        logger.info("BDD paper trading initialisée.")
    except Exception as e:
        logger.error(f"Erreur init paper DB : {e}")
        raise


def creer_position(p: dict) -> int:
    """Insert une nouvelle position OPEN. Retourne l'id créé."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO positions
            (ticker, asset_type, direction, entry_price, entry_date, quantity,
             invested_amount, stop_loss, target_1, target_2, confidence,
             entry_reason, signals_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["ticker"], p.get("asset_type"), p["direction"],
        p["entry_price"], p.get("entry_date", _now_iso()), p["quantity"],
        p["invested_amount"], p["stop_loss"], p["target_1"], p.get("target_2"),
        p.get("confidence"), p.get("entry_reason"), p.get("signals_used"),
    ))
    pos_id = c.lastrowid
    c.execute("""
        INSERT INTO transactions (position_id, type, ticker, price, quantity, amount, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (pos_id, "BUY" if p["direction"] == "LONG" else "SELL_SHORT",
          p["ticker"], p["entry_price"], p["quantity"], p["invested_amount"], _now_iso()))
    conn.commit()
    conn.close()
    return pos_id


def fermer_position(pos_id: int, exit_price: float, raison: str, status: str) -> dict | None:
    """Met à jour la position et enregistre la transaction de sortie."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    p = dict(row)
    if p["direction"] == "LONG":
        pnl_euros = (exit_price - p["entry_price"]) * p["quantity"]
    else:
        pnl_euros = (p["entry_price"] - exit_price) * p["quantity"]
    pnl_pct = (pnl_euros / p["invested_amount"] * 100) if p["invested_amount"] else 0

    c.execute("""
        UPDATE positions
        SET status = ?, exit_price = ?, exit_date = ?, pnl_euros = ?, pnl_percent = ?, exit_reason = ?
        WHERE id = ?
    """, (status, exit_price, _now_iso(), pnl_euros, pnl_pct, raison, pos_id))
    c.execute("""
        INSERT INTO transactions (position_id, type, ticker, price, quantity, amount, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (pos_id, "SELL" if p["direction"] == "LONG" else "BUY_COVER",
          p["ticker"], exit_price, p["quantity"], exit_price * p["quantity"], _now_iso()))
    conn.commit()
    conn.close()
    return {"pnl_euros": pnl_euros, "pnl_percent": pnl_pct, "ticker": p["ticker"],
            "direction": p["direction"], "entry_price": p["entry_price"]}


def lire_positions_ouvertes() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY entry_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def lire_position_ouverte_actif(ticker: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM positions WHERE ticker = ? AND status = 'OPEN'", (ticker,)).fetchone()
    conn.close()
    return dict(row) if row else None


def lire_positions_recentes_fermees(limite: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status != 'OPEN' ORDER BY exit_date DESC LIMIT ?",
        (limite,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def enregistrer_snapshot(snap: dict) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO portfolio_snapshots
            (date, cash, invested, unrealized_pnl, total_value,
             daily_return_percent, cumulative_return_percent, open_positions_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (snap["date"], snap["cash"], snap["invested"], snap["unrealized_pnl"],
          snap["total_value"], snap.get("daily_return_percent"),
          snap.get("cumulative_return_percent"), snap.get("open_positions_count", 0)))
    conn.commit()
    conn.close()


def lire_dernier_snapshot() -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM portfolio_snapshots ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None
