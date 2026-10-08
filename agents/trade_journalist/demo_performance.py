"""
agents/trade_journalist/demo_performance.py — Démonstration du Trade Journalist, isolée.

Jusqu'au 08/10/2026, le bloc __main__ de performance_tracker.py écrivait ses
signaux fictifs (SIG-0001 à SIG-0005, dont 3 clôturés) dans data/database.db et
réécrivait memory/performance_tracker.md : des décisions de production ont lu
ces statistiques (docs/TODO.md, signal_results). La démo tourne désormais dans
un dossier temporaire (base SQLite + fichiers mémoire), supprimé à la fin.

Lancement : python -m agents.trade_journalist.performance_tracker
"""

import os
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils import database
from utils.logger import get_logger
from utils.portfolio_db import initialiser_paper_db
from agents.trade_journalist import journalist, performance_tracker, intuition_tracker, learner

logger = get_logger(__name__)

# Valeurs du __main__ d'origine (relues par scripts/purger_signaux_demo.py)
SIGNAUX_DEMO = [
    ("BTC-USD", "LONG",  8, 71349.71, 67743.60, 78561.93, 82168.04, "1d", "Market+Fundamental", "EMA bullish + BTC sous-évalué"),
    ("ETH-USD", "LONG",  6, 3200.00,   3048.52,  3502.97,  3654.45, "1d", "Market",             "Double bottom daily"),
    ("AAPL",    "LONG",  7, 260.48,    254.58,   272.28,   278.18, "1d", "Market+Fundamental", "Tendance EMA haussière"),
    ("SOL-USD", "SHORT", 5, 210.00,    218.00,   194.00,   186.00, "1d", "Market",             "Double top 4H"),
    ("SPY",     "LONG",  6, 679.46,    671.40,   695.58,   703.64, "1d", "Fundamental+Sentiment","Macro saine, courbe normale"),
]
# (rang dans SIGNAUX_DEMO, prix de sortie, leçon) : 2 gagnants, 1 perdant
CLOTURES_DEMO = [
    (0, 78561.93, "Target 1 BTC atteint, trade gagnant"),   # +10%
    (1, 3050.00,  "Stop-loss ETH touché, trend reversal"),  # -4.6%
    (2, 275.00,   "AAPL target 1 atteint"),                 # +5.6%
]

# Tout ce que la démo écrit, redirigé vers le dossier temporaire
_CHEMINS = [(database, "DB_PATH", "database.db"),
            (journalist, "JOURNAL_FILE", "trade_journal.md"),
            (performance_tracker, "PERFORMANCE_FILE", "performance_tracker.md"),
            (performance_tracker, "LESSONS_LEARNED_FILE", "lessons_learned.md"),
            (intuition_tracker, "INTUITION_LOG", "intuition_log.md"),
            (learner, "PATTERNS_MD", "market_patterns.md"),
            (learner, "LESSONS_MD", "lessons_learned.md")]


@contextmanager
def environnement_isole():
    """Base SQLite (tables créées) et fichiers mémoire dans un dossier temporaire,
    le temps du bloc. Rend le dossier ; chemins restaurés et dossier supprimé à la sortie."""
    with tempfile.TemporaryDirectory(prefix="alphasignal_demo_", ignore_cleanup_errors=True) as dossier, \
            ExitStack() as pile:
        for module, attribut, nom in _CHEMINS:
            pile.enter_context(mock.patch.object(module, attribut, os.path.join(dossier, nom)))
        database.initialiser_base()
        initialiser_paper_db()  # positions : lues par auto_apprendre via mettre_a_jour_performance_md
        yield dossier


def inserer_donnees_demo() -> list[str]:
    """Les 5 signaux et les 3 clôtures de la démo, dans la base courante. Rend les identifiants."""
    ids = [sid for sid in (journalist.enregistrer_signal(*s) for s in SIGNAUX_DEMO) if sid]
    if len(ids) >= 3:
        for rang, prix_sortie, lecon in CLOTURES_DEMO:
            journalist.cloturer_signal(ids[rang], prix_sortie, lecon)
    return ids


def lancer_demo() -> dict:
    """Test du module : 5 signaux simulés, 3 clôtures, rapport de performance, en isolation."""
    print("\nAlphaSignal — Trade Journalist — Test\n")
    with environnement_isole() as dossier:
        print(f"Démo isolée dans {dossier} : rien n'est écrit dans data/ ni dans memory/\n")
        logger.info(f"Démo isolée ({dossier}) : les signaux journalisés ensuite n'existent pas dans data/database.db")
        inserer_donnees_demo()
        performance_tracker.mettre_a_jour_performance_md()
        stats = performance_tracker.calculer_stats_globales()
        print("Stats globales :", stats)
        print("\nStats par actif :")
        for s in performance_tracker.stats_par_actif():
            print(f"  {s['ticker']:10s} — {s['total']} trades, win rate {s['win_rate']:.1f}%, "
                  f"P&L moyen {s['avg_pnl']:+.2f}%")
        alerte, msg = performance_tracker.verifier_alerte_degradation()
        if alerte:
            print(f"\n{msg}")
        else:
            print(f"\nPas d'alerte dégradation (seuil {performance_tracker.SEUIL_ALERTE_WINRATE}% sur 20 trades)")
    return stats
