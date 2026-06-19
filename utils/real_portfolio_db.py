"""
utils/real_portfolio_db.py — BDD du portefeuille RÉEL (v5.0)
Totalement séparé du paper trading. L'utilisateur saisit manuellement.
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


def initialiser_real_db() -> None:
    """Crée les 2 tables real_investments + real_advice_log si absentes."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS real_investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                asset_name TEXT,
                holding_type TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                direction TEXT DEFAULT 'LONG',
                entry_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                quantity REAL NOT NULL,
                invested_amount REAL NOT NULL,
                leverage REAL DEFAULT 1,
                target_price REAL,
                stop_loss_mental REAL,
                investment_thesis TEXT,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_date TEXT,
                realized_pnl REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS real_advice_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_id INTEGER,
                advice_date TEXT NOT NULL,
                advice_type TEXT,
                recommendation TEXT,
                reasoning TEXT,
                urgency TEXT,
                user_decision TEXT,
                user_decision_date TEXT,
                FOREIGN KEY (investment_id) REFERENCES real_investments(id)
            )
        """)
        conn.commit()
        conn.close()
        logger.info("BDD portefeuille réel initialisée")
    except Exception as e:
        logger.error(f"Erreur init real DB : {e}")
        raise


# ── CRUD investissements ────────────────────────────────────────────────────

def ajouter_investissement(p: dict) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO real_investments
        (asset, asset_name, holding_type, instrument_type, direction,
         entry_price, entry_date, quantity, invested_amount, leverage,
         target_price, stop_loss_mental, investment_thesis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["asset"], p.get("asset_name"), p["holding_type"], p["instrument_type"],
        p.get("direction", "LONG"), p["entry_price"], p.get("entry_date", _now_iso()),
        p["quantity"], p["invested_amount"], p.get("leverage", 1),
        p.get("target_price"), p.get("stop_loss_mental"), p.get("investment_thesis"),
    ))
    pos_id = c.lastrowid
    conn.commit()
    conn.close()
    return pos_id


def fermer_investissement(inv_id: int, exit_price: float, notes: str = "") -> dict | None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM real_investments WHERE id = ?", (inv_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    inv = dict(row)
    if inv["direction"] == "LONG":
        pnl = (exit_price - inv["entry_price"]) * inv["quantity"]
    else:
        pnl = (inv["entry_price"] - exit_price) * inv["quantity"]
    c.execute("""
        UPDATE real_investments
        SET status='CLOSED', exit_price=?, exit_date=?, realized_pnl=?, notes=?, updated_at=?
        WHERE id=?
    """, (exit_price, _now_iso(), pnl, notes, _now_iso(), inv_id))
    conn.commit()
    conn.close()
    return {"realized_pnl": pnl, "asset": inv["asset"]}


def supprimer_investissement(inv_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM real_investments WHERE id = ?", (inv_id,))
    n = c.rowcount
    c.execute("DELETE FROM real_advice_log WHERE investment_id = ?", (inv_id,))
    conn.commit()
    conn.close()
    return n > 0


def lire_investissements(filtre_status: str | None = None,
                         filtre_holding: str | None = None,
                         filtre_instrument: str | None = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM real_investments"
    conditions, params = [], []
    if filtre_status:
        conditions.append("status = ?")
        params.append(filtre_status)
    if filtre_holding:
        conditions.append("holding_type = ?")
        params.append(filtre_holding)
    if filtre_instrument:
        conditions.append("instrument_type = ?")
        params.append(filtre_instrument)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Conseils ────────────────────────────────────────────────────────────────

def ajouter_conseil(investment_id: int, advice_type: str, recommendation: str,
                    reasoning: str, urgency: str = "moyenne") -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO real_advice_log (investment_id, advice_date, advice_type,
                                     recommendation, reasoning, urgency)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (investment_id, _now_iso(), advice_type, recommendation, reasoning, urgency))
    advice_id = c.lastrowid
    conn.commit()
    conn.close()
    return advice_id


def enregistrer_decision_user(advice_id: int, decision: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE real_advice_log SET user_decision=?, user_decision_date=? WHERE id=?
    """, (decision, _now_iso(), advice_id))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def lire_conseils_actifs() -> list[dict]:
    """Conseils non encore répondus par l'utilisateur."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, i.asset, i.asset_name
        FROM real_advice_log a
        LEFT JOIN real_investments i ON a.investment_id = i.id
        WHERE a.user_decision IS NULL
        ORDER BY a.advice_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resume_portefeuille() -> dict:
    """Stats globales du portefeuille réel."""
    invs = lire_investissements(filtre_status="OPEN")
    invested = sum(i["invested_amount"] for i in invs)
    realized = sum((c["realized_pnl"] or 0) for c in lire_investissements(filtre_status="CLOSED"))
    return {
        "open_count":   len(invs),
        "total_invested": invested,
        "realized_pnl": realized,
    }
