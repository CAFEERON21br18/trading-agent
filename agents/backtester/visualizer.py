"""
agents/backtester/visualizer.py — Génération des graphiques de performance
Equity curve + drawdown curve sauvegardés en PNG dans strategies/backtest_results/
"""

import sys
import os
import matplotlib
matplotlib.use("Agg")  # Backend non-interactif (pas besoin d'affichage)
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "strategies", "backtest_results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def generer_graphique_equity(equity: pd.Series, titre: str,
                             nom_fichier: str, capital_initial: float = 1000) -> str:
    """Génère un graphique combiné equity + drawdown."""
    if equity.empty:
        return ""

    # Calcul drawdown
    equity_cum_max = equity.cummax()
    drawdown       = (equity - equity_cum_max) / equity_cum_max * 100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                     gridspec_kw={"height_ratios": [3, 1]})

    # Equity curve
    ax1.plot(equity.index, equity.values, linewidth=1.5, color="#2E86AB")
    ax1.axhline(y=capital_initial, color="gray", linestyle="--", alpha=0.5,
                label=f"Capital initial ({capital_initial:.0f}€)")
    ax1.fill_between(equity.index, equity.values, capital_initial,
                     where=(equity.values >= capital_initial), color="green", alpha=0.15)
    ax1.fill_between(equity.index, equity.values, capital_initial,
                     where=(equity.values < capital_initial), color="red", alpha=0.15)
    ax1.set_ylabel("Capital (€)", fontsize=11)
    ax1.set_title(titre, fontsize=13, fontweight="bold")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    # Drawdown
    ax2.fill_between(drawdown.index, drawdown.values, 0, color="red", alpha=0.4)
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    chemin = os.path.join(RESULTS_DIR, nom_fichier)
    plt.savefig(chemin, dpi=100, bbox_inches="tight")
    plt.close()

    logger.info(f"Graphique sauvegardé : {chemin}")
    return chemin


def generer_rapport_backtest(resultats: list[dict], ticker: str) -> str:
    """Génère un rapport Markdown complet et sauvegarde les graphiques des meilleures stratégies."""
    if not resultats:
        return f"# Backtest {ticker}\n\nAucun résultat."

    lignes = [f"# Backtest — {ticker}", ""]
    lignes.append("| Rang | Stratégie | Trades | Win rate | Rendement | Sharpe | Max DD |")
    lignes.append("|------|-----------|--------|----------|-----------|--------|--------|")

    for i, r in enumerate(resultats, 1):
        m = r["metriques"]
        lignes.append(
            f"| {i} | {r['nom_strategie']} | {m['nb_trades']} | "
            f"{m['win_rate']:.1f}% | {m['rendement_total_pct']:+.1f}% | "
            f"{m['sharpe_ratio']:.2f} | {m['max_drawdown_pct']:.1f}% |"
        )

    lignes.append("")
    lignes.append(f"Buy & Hold référence : {resultats[0]['rendement_bh']:+.2f}%")
    lignes.append("")

    # Graphique de la meilleure stratégie
    meilleure = resultats[0]
    if not meilleure["equity"].empty:
        nom_png = f"{ticker.replace('-','_')}_{meilleure['nom_strategie'].replace(' ','_').replace('/','_')}.png"
        chemin = generer_graphique_equity(
            meilleure["equity"],
            f"{ticker} — {meilleure['nom_strategie']}",
            nom_png,
        )
        if chemin:
            lignes.append(f"![Equity curve]({os.path.basename(chemin)})")

    return "\n".join(lignes)
