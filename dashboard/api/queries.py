"""
dashboard/api/queries.py — Requêtes SQL pour le dashboard
Lecture seule sur la BDD AlphaSignal.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.database import get_connection


def portfolio_resume() -> dict:
    """Snapshot du portefeuille + dernier état."""
    from agents.paper_trader.portfolio import etat_portefeuille
    return etat_portefeuille(prix_courants={})  # pas d'appel yfinance ici, lecture rapide


def equity_curve(limite: int = 90) -> list[dict]:
    """Snapshots des N derniers jours pour l'equity curve."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT date, total_value, cash, invested, unrealized_pnl,
               daily_return_percent, cumulative_return_percent
        FROM portfolio_snapshots
        ORDER BY date DESC LIMIT ?
    """, (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def positions(filtre_status: str | None = None, filtre_type: str | None = None) -> list[dict]:
    """Liste des positions avec filtres optionnels."""
    sql = "SELECT * FROM positions"
    conditions, params = [], []
    if filtre_status:
        conditions.append("status = ?")
        params.append(filtre_status)
    if filtre_type:
        conditions.append("asset_type = ?")
        params.append(filtre_type)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY COALESCE(exit_date, entry_date) DESC LIMIT 100"
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def position_detail(pos_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM positions WHERE id = ?", (pos_id,)).fetchone()
    if not row:
        conn.close()
        return None
    pos = dict(row)
    txs = conn.execute("SELECT * FROM transactions WHERE position_id = ?", (pos_id,)).fetchall()
    conn.close()
    pos["transactions"] = [dict(t) for t in txs]
    return pos


def watchlist() -> dict:
    chemin = os.path.join(config.BASE_DIR, "data", "watchlist.json")
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def journal_trades(limite: int = 50) -> list[dict]:
    """Combine signals + signal_results pour le journal historique."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.signal_id, s.ticker, s.direction, s.confidence, s.price_at_signal,
               s.stop_loss, s.target_1, s.target_2, s.reason, s.timestamp,
               r.exit_price, r.pnl_pct, r.duration, r.correct, r.lesson, r.closed_at
        FROM signals s
        LEFT JOIN signal_results r ON s.signal_id = r.signal_id
        ORDER BY s.timestamp DESC LIMIT ?
    """, (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def performance_globale() -> dict:
    """Stats globales depuis les positions paper et signals fermés."""
    conn = get_connection()
    # Positions paper fermées
    pos_fermees = conn.execute("""
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN pnl_euros > 0 THEN 1 ELSE 0 END) AS gagnants,
               SUM(pnl_euros) AS pnl_total,
               AVG(pnl_percent) AS pnl_moyen,
               MAX(pnl_percent) AS meilleur,
               MIN(pnl_percent) AS pire
        FROM positions WHERE status != 'OPEN'
    """).fetchone()
    paper_pos = dict(pos_fermees) if pos_fermees else {}
    # Signaux historiques (ancien système)
    sig = conn.execute("""
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN r.correct = 'CORRECT' THEN 1 ELSE 0 END) AS gagnants,
               AVG(r.pnl_pct) AS pnl_moyen
        FROM signals s LEFT JOIN signal_results r ON s.signal_id = r.signal_id
        WHERE r.signal_id IS NOT NULL
    """).fetchone()
    sig_data = dict(sig) if sig else {}
    conn.close()
    return {"paper": paper_pos, "signals": sig_data}


def fichier_memoire(nom: str) -> str:
    chemin = os.path.join(config.MEMORY_DIR, nom)
    if not os.path.exists(chemin):
        return ""
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def health() -> dict:
    """Statut système (heartbeat) + détail par cycle (v4.1)."""
    from utils.heartbeat import evaluer_sante, lire_heartbeat, evaluer_sante_cycles
    sante = evaluer_sante()
    hb = lire_heartbeat()
    cycles = evaluer_sante_cycles()
    return {
        **sante,
        "cycles":     cycles,
        "explorers":  hb.get("explorers", {}),
        "heartbeat":  hb,
    }
