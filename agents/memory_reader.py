"""
agents/memory_reader.py — Lecture structurée des fichiers mémoire
Utilisé par le Decision Engine pour intégrer l'historique dans la décision.
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")


def _lire_fichier(nom: str) -> str:
    chemin = os.path.join(MEMORY_DIR, nom)
    if not os.path.exists(chemin):
        return ""
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Lecture {nom} impossible : {e}")
        return ""


def lire_winrate_par_actif(ticker: str) -> dict | None:
    """
    Parse la table 'Performance par actif' de performance_tracker.md.
    Retourne {"trades": int, "winrate_pct": float, "pnl_moyen_pct": float} ou None.
    """
    contenu = _lire_fichier("performance_tracker.md")
    if not contenu:
        return None

    # Cherche une ligne de table avec le ticker (ex: "| BTC-USD | 1 | 1 | 100.0% | +10.11% |")
    pattern = re.compile(rf"\|\s*{re.escape(ticker)}\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*([\d.]+)%\s*\|\s*([+-]?[\d.]+)%\s*\|")
    m = pattern.search(contenu)
    if not m:
        return None
    return {
        "trades":          int(m.group(1)),
        "winrate_pct":     float(m.group(2)),
        "pnl_moyen_pct":   float(m.group(3)),
    }


def chercher_lecons(ticker: str, max_lecons: int = 5) -> list[str]:
    """Retourne les lignes de lessons_learned.md mentionnant le ticker."""
    contenu = _lire_fichier("lessons_learned.md")
    if not contenu:
        return []
    lecons = []
    for ligne in contenu.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or ligne.startswith(">") or ligne.startswith("<!--"):
            continue
        if ticker.lower() in ligne.lower() or ticker.split("-")[0].lower() in ligne.lower():
            lecons.append(ligne)
            if len(lecons) >= max_lecons:
                break
    return lecons


def chercher_patterns(ticker: str, max_patterns: int = 3) -> list[str]:
    """Retourne les patterns de market_patterns.md liés au ticker."""
    contenu = _lire_fichier("market_patterns.md")
    if not contenu:
        return []
    patterns = []
    bloc_courant = []
    for ligne in contenu.splitlines():
        if ligne.strip().startswith("---") or ligne.strip().startswith("##"):
            if bloc_courant and any(ticker.lower() in l.lower() for l in bloc_courant):
                patterns.append("\n".join(bloc_courant).strip())
            bloc_courant = []
        else:
            bloc_courant.append(ligne)
    if bloc_courant and any(ticker.lower() in l.lower() for l in bloc_courant):
        patterns.append("\n".join(bloc_courant).strip())
    return patterns[:max_patterns]


def consulter_memoire(ticker: str) -> dict:
    """
    Agrégat des données mémoire pour un ticker.
    Retourne {"perf": dict|None, "lecons": list[str], "patterns": list[str]}.
    """
    return {
        "perf":     lire_winrate_par_actif(ticker),
        "lecons":   chercher_lecons(ticker),
        "patterns": chercher_patterns(ticker),
    }
