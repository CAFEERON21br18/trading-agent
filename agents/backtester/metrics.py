"""
agents/backtester/metrics.py — Calcul des métriques de performance d'un backtest
Métriques : win rate, profit factor, max drawdown, Sharpe ratio, rendement total.
"""

import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def calculer_metriques(trades: list[dict], equity_curve: pd.Series,
                       capital_initial: float) -> dict:
    """
    Calcule toutes les métriques de performance à partir des trades et de l'equity.
    trades : [{entry_date, exit_date, direction, entry_price, exit_price, pnl, pnl_pct}, ...]
    equity_curve : pd.Series indexée par date, valeur = equity au cours du temps
    """
    if not trades or equity_curve.empty:
        return {
            "nb_trades": 0, "win_rate": 0, "profit_factor": 0,
            "rendement_total_pct": 0, "sharpe_ratio": 0,
            "max_drawdown_pct": 0, "avg_win_pct": 0, "avg_loss_pct": 0,
            "capital_final": capital_initial,
        }

    pnls_pct = [t["pnl_pct"] for t in trades]
    gagnants = [p for p in pnls_pct if p > 0]
    perdants = [p for p in pnls_pct if p <= 0]

    win_rate  = len(gagnants) / len(trades) * 100 if trades else 0
    avg_win   = np.mean(gagnants) if gagnants else 0
    avg_loss  = np.mean(perdants) if perdants else 0

    # Profit factor = somme gains / |somme pertes|
    total_gains  = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    total_pertes = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = total_gains / total_pertes if total_pertes > 0 else float("inf")

    # Rendement total
    capital_final = float(equity_curve.iloc[-1])
    rendement_total_pct = (capital_final - capital_initial) / capital_initial * 100

    # Sharpe ratio annualisé (rendements journaliers, risk-free 0%)
    rendements = equity_curve.pct_change().dropna()
    if len(rendements) > 1 and rendements.std() > 0:
        # 252 jours de trading par an — approximation
        sharpe_ratio = (rendements.mean() / rendements.std()) * np.sqrt(252)
    else:
        sharpe_ratio = 0

    # Max drawdown
    equity_cum_max  = equity_curve.cummax()
    drawdown_series = (equity_curve - equity_cum_max) / equity_cum_max
    max_drawdown_pct = abs(drawdown_series.min() * 100) if not drawdown_series.empty else 0

    return {
        "nb_trades":          len(trades),
        "nb_gagnants":        len(gagnants),
        "nb_perdants":        len(perdants),
        "win_rate":           win_rate,
        "profit_factor":      profit_factor,
        "rendement_total_pct": rendement_total_pct,
        "sharpe_ratio":       sharpe_ratio,
        "max_drawdown_pct":   max_drawdown_pct,
        "avg_win_pct":        avg_win,
        "avg_loss_pct":       avg_loss,
        "capital_final":      capital_final,
    }


def formater_metriques(metriques: dict, nom_strategie: str, ticker: str,
                       rendement_bh_pct: float | None = None) -> str:
    """Formatte les métriques en rapport lisible."""
    pf_str = f"{metriques['profit_factor']:.2f}" if metriques['profit_factor'] != float('inf') else "∞"

    verdict = "❌ Non rentable"
    if metriques["rendement_total_pct"] > 0 and metriques["profit_factor"] >= 1.5 and metriques["win_rate"] >= 45:
        verdict = "✅ Viable"
    elif metriques["rendement_total_pct"] > 0:
        verdict = "⚠️ À optimiser"

    lignes = [
        f"Stratégie     : {nom_strategie}",
        f"Actif         : {ticker}",
        "─" * 50,
        f"Trades        : {metriques['nb_trades']} ({metriques['nb_gagnants']}G / {metriques['nb_perdants']}P)",
        f"Win rate      : {metriques['win_rate']:.1f}%",
        f"Profit factor : {pf_str}",
        f"Sharpe ratio  : {metriques['sharpe_ratio']:.2f}",
        f"Max drawdown  : {metriques['max_drawdown_pct']:.2f}%",
        f"Avg win       : {metriques['avg_win_pct']:+.2f}%",
        f"Avg loss      : {metriques['avg_loss_pct']:+.2f}%",
        "─" * 50,
        f"Capital final : {metriques['capital_final']:,.2f}€",
        f"Rendement     : {metriques['rendement_total_pct']:+.2f}%",
    ]
    if rendement_bh_pct is not None:
        lignes.append(f"Buy & Hold    : {rendement_bh_pct:+.2f}%")
        delta = metriques['rendement_total_pct'] - rendement_bh_pct
        lignes.append(f"vs B&H        : {delta:+.2f}%")
    lignes.append("─" * 50)
    lignes.append(f"Verdict       : {verdict}")
    return "\n".join(lignes)
