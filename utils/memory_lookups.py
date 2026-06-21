"""
utils/memory_lookups.py — Requêtes mémoire pour les skills de raisonnement (v5.3.9).
Fournit des helpers ciblés pour le pipeline de décision : winrate par actif,
pertes consécutives récentes, setups similaires.
Tout est tolérant : retourne None ou liste vide si la donnée manque.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.database import get_connection

logger = get_logger(__name__)


def winrate_par_actif(ticker: str) -> dict | None:
    """Stats du ticker : total trades, gagnants, winrate, P&L moyen. None si < 3 trades."""
    try:
        conn = get_connection()
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN r.pnl_pct > 0 THEN 1 ELSE 0 END) AS gagnants,
                   AVG(r.pnl_pct) AS avg_pnl,
                   MIN(r.pnl_pct) AS worst,
                   MAX(r.pnl_pct) AS best
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            WHERE s.ticker = ?
        """, (ticker,)).fetchone()
        conn.close()
        if not row or (row["total"] or 0) < 3:
            return None
        total    = row["total"]
        gagnants = row["gagnants"] or 0
        return {
            "ticker":      ticker,
            "total":       total,
            "gagnants":    gagnants,
            "winrate_pct": round(gagnants / total * 100, 1),
            "avg_pnl":     round(row["avg_pnl"] or 0, 2),
            "best":        round(row["best"] or 0, 2),
            "worst":       round(row["worst"] or 0, 2),
        }
    except Exception as e:
        logger.warning(f"winrate_par_actif {ticker} : {e}")
        return None


def winrate_recent(n: int = 20) -> dict | None:
    """Stats globales sur les N derniers trades clôturés."""
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT r.pnl_pct
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            WHERE r.pnl_pct IS NOT NULL
            ORDER BY s.timestamp DESC LIMIT ?
        """, (n,)).fetchall()
        conn.close()
        if not rows:
            return None
        pnls = [r["pnl_pct"] for r in rows]
        gagnants = [p for p in pnls if p > 0]
        return {
            "echantillon": len(pnls),
            "gagnants":    len(gagnants),
            "winrate_pct": round(len(gagnants) / len(pnls) * 100, 1),
            "avg_pnl":     round(sum(pnls) / len(pnls), 2),
        }
    except Exception as e:
        logger.warning(f"winrate_recent : {e}")
        return None


def pertes_consecutives_recentes() -> int:
    """Nombre de pertes consécutives en partant du trade le plus récent."""
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT r.pnl_pct
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            WHERE r.pnl_pct IS NOT NULL
            ORDER BY s.timestamp DESC LIMIT 10
        """).fetchall()
        conn.close()
        consec = 0
        for r in rows:
            if (r["pnl_pct"] or 0) < 0:
                consec += 1
            else:
                break
        return consec
    except Exception as e:
        logger.warning(f"pertes_consecutives_recentes : {e}")
        return 0


def setups_similaires(direction: str, asset_class: str | None = None,
                       limit: int = 20) -> list[dict]:
    """Trades passés avec même direction (et classe d'actif si fournie).
    Sert de "classe de référence" pour le skill base_rates."""
    try:
        conn = get_connection()
        params: list = [direction.upper()]
        sql = """
            SELECT s.ticker, s.direction, r.pnl_pct, s.timestamp
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            WHERE UPPER(s.direction) = ? AND r.pnl_pct IS NOT NULL
        """
        if asset_class == "crypto":
            sql += " AND s.ticker LIKE '%-USD'"
            sql += " ORDER BY s.timestamp DESC LIMIT ?"
            params.append(limit)
        elif asset_class == "stock":
            sql += " AND s.ticker NOT LIKE '%-USD' AND s.ticker NOT LIKE '%=F'"
            sql += " ORDER BY s.timestamp DESC LIMIT ?"
            params.append(limit)
        else:
            sql += " ORDER BY s.timestamp DESC LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"setups_similaires : {e}")
        return []


def classifier_actif(ticker: str) -> str:
    """Renvoie la classe d'actif : crypto / stock / future / forex."""
    t = (ticker or "").upper()
    if t.endswith("-USD"):
        return "crypto"
    if t.endswith("=F"):
        return "future"
    if t.endswith("=X"):
        return "forex"
    return "stock"
