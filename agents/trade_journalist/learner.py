"""
agents/trade_journalist/learner.py — Auto-amélioration de la mémoire
Analyse l'historique des positions et écrit automatiquement :
- Patterns récurrents (3+ occurrences) → market_patterns.md
- Leçons d'erreur (3+ pertes même actif/conditions) → lessons_learned.md
"""

import sys
import os
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.portfolio_db import lire_positions_recentes_fermees

logger = get_logger(__name__)

MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "memory",
)
PATTERNS_MD = os.path.join(MEMORY_DIR, "market_patterns.md")
LESSONS_MD  = os.path.join(MEMORY_DIR, "lessons_learned.md")

SEUIL_PATTERN_RECURRENT = 3   # 3 occurrences pour identifier un pattern
SEUIL_PERTES_ACTIF      = 3   # 3 pertes sur même actif → leçon


def _maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _lire(chemin: str) -> str:
    if not os.path.exists(chemin):
        return ""
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ajouter_si_nouveau(chemin: str, marqueur_unique: str, nouvelle_entree: str) -> bool:
    """Ajoute l'entrée seulement si `marqueur_unique` n'est pas déjà dans le fichier."""
    contenu = _lire(chemin)
    if marqueur_unique in contenu:
        return False
    try:
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("\n" + nouvelle_entree.strip() + "\n")
        return True
    except Exception as e:
        logger.error(f"Écriture mémoire {chemin} : {e}")
        return False


def detecter_patterns(positions: list[dict] | None = None) -> int:
    """
    Détecte les patterns récurrents : couples (actif, direction) avec 3+ trades fermés.
    Retourne le nb d'entrées ajoutées à market_patterns.md.
    """
    if positions is None:
        positions = lire_positions_recentes_fermees(limite=100)
    if not positions:
        return 0

    compte = Counter((p["ticker"], p["direction"]) for p in positions)
    ajoutees = 0
    today = _maintenant()
    for (ticker, direction), n in compte.items():
        if n < SEUIL_PATTERN_RECURRENT:
            continue
        # Statistiques pour ce couple
        sous = [p for p in positions if p["ticker"] == ticker and p["direction"] == direction]
        wins = sum(1 for p in sous if (p.get("pnl_euros") or 0) > 0)
        wr = wins / n * 100
        pnl_moy = sum((p.get("pnl_percent") or 0) for p in sous) / n

        marqueur = f"PATTERN-{ticker}-{direction}"
        entree = f"""
{today} — {ticker} — Pattern récurrent {direction}  ({marqueur})
- Observé : {n} fois
- Win rate : {wr:.0f}%
- P&L moyen : {pnl_moy:+.2f}%
- Fiabilité estimée : {'Forte' if wr >= 65 else 'Moyenne' if wr >= 45 else 'Faible'}
"""
        if _ajouter_si_nouveau(PATTERNS_MD, marqueur, entree):
            ajoutees += 1
            logger.info(f"Pattern détecté → {ticker} {direction} ({n} occurrences, wr {wr:.0f}%)")
    return ajoutees


def detecter_lecons(positions: list[dict] | None = None) -> int:
    """
    Détecte les actifs avec 3+ pertes récentes → écrit une leçon de prudence.
    Retourne le nb de leçons ajoutées.
    """
    if positions is None:
        positions = lire_positions_recentes_fermees(limite=50)
    if not positions:
        return 0

    pertes_par_actif = Counter()
    for p in positions:
        if (p.get("pnl_euros") or 0) < 0:
            pertes_par_actif[p["ticker"]] += 1

    today = _maintenant()
    ajoutees = 0
    for ticker, nb in pertes_par_actif.items():
        if nb < SEUIL_PERTES_ACTIF:
            continue
        marqueur = f"LECON-PERTES-{ticker}-{today[:7]}"  # 1 leçon par mois
        entree = f"""
`{today} — RISQUE — {ticker} : {nb} pertes récentes détectées sur cet actif. \
Augmenter la prudence (confiance min 8/10 ou éviter temporairement).` ({marqueur})
"""
        if _ajouter_si_nouveau(LESSONS_MD, marqueur, entree):
            ajoutees += 1
            logger.info(f"Leçon générée pour {ticker} ({nb} pertes)")
    return ajoutees


def auto_apprendre() -> dict:
    """Lance les 2 détections (à appeler dans le cycle de performance update)."""
    positions = lire_positions_recentes_fermees(limite=100)
    nb_patterns = detecter_patterns(positions)
    nb_lecons   = detecter_lecons(positions)
    return {"patterns_ajoutes": nb_patterns, "lecons_ajoutees": nb_lecons,
            "trades_analysés": len(positions)}
