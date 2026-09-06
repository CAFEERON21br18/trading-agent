"""
agents/technical_skills/performance_attribution.py — Skill 10 : attribution.

Décompose la performance des trades fermés selon plusieurs axes pour
identifier "d'où viennent" gains et pertes → doubler sur ce qui marche.

Axes d'attribution :
- par classe d'actif (crypto / action / cfd / etf)
- par direction (LONG / SHORT)
- par statut de sortie (TP / SL / REVERSAL)
- par ticker (top / worst)

Python pur, aucun LLM.
"""

import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger   import get_logger
from utils.database import get_connection

logger = get_logger(__name__)


def _stats_groupe(rows: list[dict]) -> dict:
    """Calcule les stats agrégées d'un groupe de trades fermés."""
    if not rows:
        return {"nb_trades": 0, "win_rate": 0, "pnl_total_euros": 0,
                "pnl_moyen_pct": 0, "gagnants": 0, "perdants": 0}
    pnls = [r.get("pnl_euros") or 0 for r in rows]
    pcts = [r.get("pnl_percent") or 0 for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    return {
        "nb_trades":       len(pnls),
        "gagnants":        wins,
        "perdants":        len(pnls) - wins,
        "win_rate":        round(wins / len(pnls) * 100, 1),
        "pnl_total_euros": round(total, 2),
        "pnl_moyen_pct":   round(sum(pcts) / len(pcts), 2),
        "meilleur_pnl":    round(max(pnls), 2),
        "pire_pnl":        round(min(pnls), 2),
    }


def attribution_par_axe(axe: str, limite_trades: int = 500) -> dict:
    """Retourne l'attribution des trades fermés groupés par la colonne 'axe'.
    axes valides : asset_type, direction, status, ticker, exit_reason."""
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM positions WHERE status LIKE 'CLOSED%' "
        f"ORDER BY exit_date DESC LIMIT ?", (limite_trades,)
    ).fetchall()
    conn.close()
    trades = [dict(r) for r in rows]

    groupes: dict = defaultdict(list)
    for t in trades:
        key = t.get(axe) or "?"
        groupes[str(key)].append(t)

    result = {}
    for k, rows_k in groupes.items():
        result[k] = _stats_groupe(rows_k)
    # Tri par pnl_total décroissant
    sorted_r = dict(sorted(result.items(),
                            key=lambda kv: kv[1]["pnl_total_euros"],
                            reverse=True))
    return sorted_r


def rapport_attribution_complet(limite_trades: int = 500) -> dict:
    """Attribution multi-axes complète."""
    return {
        "par_classe_actif":   attribution_par_axe("asset_type", limite_trades),
        "par_direction":      attribution_par_axe("direction",  limite_trades),
        "par_sortie":         attribution_par_axe("status",     limite_trades),
        "par_exit_reason":    attribution_par_axe("exit_reason", limite_trades),
        "top_10_tickers":     _top_tickers(limite_trades, top_n=10),
        "flop_10_tickers":    _flop_tickers(limite_trades, flop_n=10),
        "global":             _stats_globales(limite_trades),
    }


def _top_tickers(limite: int, top_n: int = 10) -> list[dict]:
    ticker_pnl = attribution_par_axe("ticker", limite)
    tops = []
    for t, s in list(ticker_pnl.items())[:top_n]:
        if s["pnl_total_euros"] > 0:
            tops.append({"ticker": t, **s})
    return tops


def _flop_tickers(limite: int, flop_n: int = 10) -> list[dict]:
    ticker_pnl = attribution_par_axe("ticker", limite)
    reversed_items = list(reversed(list(ticker_pnl.items())))
    flops = []
    for t, s in reversed_items[:flop_n]:
        if s["pnl_total_euros"] < 0:
            flops.append({"ticker": t, **s})
    return flops


def _stats_globales(limite: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status LIKE 'CLOSED%' "
        "ORDER BY exit_date DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return _stats_groupe([dict(r) for r in rows])
