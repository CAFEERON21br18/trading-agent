"""
agents/trade_journalist/performance_tracker.py — Suivi des performances de l'agent
Calcule win rate, profit factor, statistiques par actif. Met à jour la mémoire.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger   import get_logger
from utils.database import get_connection

logger = get_logger(__name__)

BASE_DIR                = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PERFORMANCE_FILE        = os.path.join(BASE_DIR, "memory", "performance_tracker.md")
LESSONS_LEARNED_FILE    = os.path.join(BASE_DIR, "memory", "lessons_learned.md")
SEUIL_ALERTE_WINRATE    = 50  # Alerte email si win rate < 50% sur les 20 derniers trades


def calculer_stats_globales(nb_derniers: int | None = None) -> dict:
    """Calcule les statistiques globales. Si nb_derniers=None, prend tout l'historique."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        query = """
            SELECT s.ticker, s.direction, s.confidence,
                   r.pnl_pct, r.correct
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            ORDER BY s.timestamp DESC
        """
        if nb_derniers:
            query += f" LIMIT {nb_derniers}"
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"nb_trades": 0, "win_rate": 0, "profit_factor": 0,
                    "avg_pnl": 0, "best": 0, "worst": 0}

        pnls      = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
        gagnants  = [p for p in pnls if p > 0]
        perdants  = [p for p in pnls if p < 0]

        win_rate  = len(gagnants) / len(pnls) * 100 if pnls else 0
        sum_g     = sum(gagnants)
        sum_p     = abs(sum(perdants))
        pf        = sum_g / sum_p if sum_p > 0 else float("inf") if sum_g > 0 else 0

        return {
            "nb_trades":     len(pnls),
            "nb_gagnants":   len(gagnants),
            "nb_perdants":   len(perdants),
            "win_rate":      win_rate,
            "profit_factor": pf,
            "avg_pnl":       sum(pnls) / len(pnls) if pnls else 0,
            "best":          max(pnls) if pnls else 0,
            "worst":         min(pnls) if pnls else 0,
        }
    except Exception as e:
        logger.error(f"Erreur stats globales : {e}")
        return {}


def stats_par_actif() -> list[dict]:
    """Calcule les stats détaillées par ticker."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.ticker,
                   COUNT(*) AS total,
                   SUM(CASE WHEN r.pnl_pct > 0 THEN 1 ELSE 0 END) AS gagnants,
                   AVG(r.pnl_pct) AS avg_pnl
            FROM signals s
            INNER JOIN signal_results r ON s.signal_id = r.signal_id
            GROUP BY s.ticker
            ORDER BY total DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        resultats = []
        for r in rows:
            total    = r["total"] or 0
            gagnants = r["gagnants"] or 0
            win_rate = gagnants / total * 100 if total > 0 else 0
            resultats.append({
                "ticker":   r["ticker"],
                "total":    total,
                "gagnants": gagnants,
                "win_rate": win_rate,
                "avg_pnl":  r["avg_pnl"] or 0,
            })
        return resultats
    except Exception as e:
        logger.error(f"Erreur stats par actif : {e}")
        return []


def verifier_alerte_degradation() -> tuple[bool, str]:
    """Vérifie si le win rate récent est en dessous du seuil critique."""
    stats = calculer_stats_globales(nb_derniers=20)
    if stats.get("nb_trades", 0) < 20:
        return False, ""
    if stats["win_rate"] < SEUIL_ALERTE_WINRATE:
        return True, (
            f"⚠️  ALERTE DÉGRADATION : win rate {stats['win_rate']:.1f}% "
            f"sur les 20 derniers trades (seuil {SEUIL_ALERTE_WINRATE}%)"
        )
    return False, ""


def mettre_a_jour_performance_md():
    """Réécrit memory/performance_tracker.md avec les stats actuelles."""
    try:
        # Synchroniser les résultats d'intuition + auto-apprentissage
        try:
            from agents.trade_journalist.intuition_tracker import synchroniser_intuition
            from agents.trade_journalist.learner import auto_apprendre
            synchroniser_intuition()
            auto_apprendre()
        except Exception as e:
            logger.error(f"Synchronisation mémoire échouée : {e}")

        stats_all    = calculer_stats_globales()
        stats_recent = calculer_stats_globales(nb_derniers=20)
        stats_actifs = stats_par_actif()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        pf_all_str    = f"{stats_all['profit_factor']:.2f}" if stats_all.get('profit_factor') != float('inf') else "∞"
        pf_recent_str = f"{stats_recent['profit_factor']:.2f}" if stats_recent.get('profit_factor') != float('inf') else "∞"

        lignes = [
            "# AlphaSignal — Performance de l'Agent",
            f"",
            f"> Dernière mise à jour : {now}",
            f"",
            f"## Performance globale (tous trades clôturés)",
            f"",
            f"| Métrique | Valeur |",
            f"|----------|--------|",
            f"| Total signaux clôturés | {stats_all.get('nb_trades', 0)} |",
            f"| Win rate | {stats_all.get('win_rate', 0):.1f}% |",
            f"| Profit factor | {pf_all_str} |",
            f"| P&L moyen / trade | {stats_all.get('avg_pnl', 0):+.2f}% |",
            f"| Meilleur trade | {stats_all.get('best', 0):+.2f}% |",
            f"| Pire trade | {stats_all.get('worst', 0):+.2f}% |",
            f"",
            f"## Performance récente (20 derniers trades)",
            f"",
            f"| Métrique | Valeur |",
            f"|----------|--------|",
            f"| Trades | {stats_recent.get('nb_trades', 0)} |",
            f"| Win rate | {stats_recent.get('win_rate', 0):.1f}% |",
            f"| Profit factor | {pf_recent_str} |",
            f"",
            f"## Performance par actif",
            f"",
            f"| Ticker | Trades | Gagnants | Win rate | P&L moyen |",
            f"|--------|--------|----------|----------|-----------|",
        ]
        for s in stats_actifs:
            lignes.append(
                f"| {s['ticker']} | {s['total']} | {s['gagnants']} | "
                f"{s['win_rate']:.1f}% | {s['avg_pnl']:+.2f}% |"
            )
        if not stats_actifs:
            lignes.append("| — | 0 | 0 | — | — |")

        with open(PERFORMANCE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes) + "\n")

        logger.info(f"Performance mise à jour : {PERFORMANCE_FILE}")
    except Exception as e:
        logger.error(f"Erreur mise à jour performance_tracker.md : {e}")


def ajouter_lecon(categorie: str, lecon: str):
    """Ajoute une leçon dans memory/lessons_learned.md."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entree = f"\n`{date} — {categorie.upper()} — {lecon}`\n"
    try:
        with open(LESSONS_LEARNED_FILE, "a", encoding="utf-8") as f:
            f.write(entree)
        logger.info(f"Leçon ajoutée ({categorie})")
    except Exception as e:
        logger.error(f"Erreur ajout leçon : {e}")


if __name__ == "__main__":
    # Test : simuler 5 signaux + clôturer 3 + générer le rapport
    from agents.trade_journalist.journalist import enregistrer_signal, cloturer_signal

    print("\nAlphaSignal — Trade Journalist — Test\n")

    # 5 signaux simulés
    signaux_test = [
        ("BTC-USD", "LONG",  8, 71349.71, 67743.60, 78561.93, 82168.04, "1d", "Market+Fundamental", "EMA bullish + BTC sous-évalué"),
        ("ETH-USD", "LONG",  6, 3200.00,   3048.52,  3502.97,  3654.45, "1d", "Market",             "Double bottom daily"),
        ("AAPL",    "LONG",  7, 260.48,    254.58,   272.28,   278.18, "1d", "Market+Fundamental", "Tendance EMA haussière"),
        ("SOL-USD", "SHORT", 5, 210.00,    218.00,   194.00,   186.00, "1d", "Market",             "Double top 4H"),
        ("SPY",     "LONG",  6, 679.46,    671.40,   695.58,   703.64, "1d", "Fundamental+Sentiment","Macro saine, courbe normale"),
    ]
    ids = []
    for args in signaux_test:
        sid = enregistrer_signal(*args)
        if sid:
            ids.append(sid)

    # Clôturer 3 trades (2 gagnants, 1 perdant)
    if len(ids) >= 3:
        cloturer_signal(ids[0], 78561.93, "Target 1 BTC atteint, trade gagnant")       # +10%
        cloturer_signal(ids[1], 3050.00,  "Stop-loss ETH touché, trend reversal")      # -4.6%
        cloturer_signal(ids[2], 275.00,   "AAPL target 1 atteint")                     # +5.6%

    mettre_a_jour_performance_md()

    print("Stats globales :", calculer_stats_globales())
    print("\nStats par actif :")
    for s in stats_par_actif():
        print(f"  {s['ticker']:10s} — {s['total']} trades, win rate {s['win_rate']:.1f}%, P&L moyen {s['avg_pnl']:+.2f}%")

    alerte, msg = verifier_alerte_degradation()
    if alerte:
        print(f"\n{msg}")
    else:
        print(f"\nPas d'alerte dégradation (seuil {SEUIL_ALERTE_WINRATE}% sur 20 trades)")
