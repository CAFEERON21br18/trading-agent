"""
agents/trade_journalist/intuition_tracker.py — Suivi rétrospectif de l'intuition
Compare les décisions intuitives passées (intuition_log.md, marquées "⏳ à remplir")
avec les positions fermées récentes, et auto-remplit le résultat (✅ / ❌).
"""

import sys
import os
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.portfolio_db import lire_positions_recentes_fermees

logger = get_logger(__name__)

INTUITION_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "memory", "intuition_log.md",
)

# Regex pour identifier une entrée et son ticker
HEADER_RE = re.compile(r"^### ([\d\-T:+ ]+UTC?) — ([A-Z\-=^.]+) — (\w+) \(intuition\)", re.MULTILINE)


def _lire_log() -> str:
    try:
        with open(INTUITION_LOG, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ecrire_log(contenu: str) -> None:
    with open(INTUITION_LOG, "w", encoding="utf-8") as f:
        f.write(contenu)


def _completer_resultat(contenu: str, ticker: str, pnl_pct: float, pnl_eur: float) -> tuple[str, bool]:
    """
    Remplace le 1er '⏳ à remplir' associé à `ticker` par le résultat réel.
    Retourne (nouveau_contenu, modifié_oui_non).
    """
    # Construire le bloc à remplacer pour CE ticker en attente
    pattern = re.compile(
        rf"(### [\d\-T:+ ]+UTC?\s+—\s+{re.escape(ticker)}\s+—.+?)(- \*\*Résultat\*\* : ⏳ à remplir après clôture)",
        re.DOTALL,
    )
    emoji = "✅" if pnl_pct >= 0 else "❌"
    remplacement = rf"\1- **Résultat** : {emoji} {pnl_pct:+.2f}% ({pnl_eur:+.2f}€)"
    nouveau = pattern.sub(remplacement, contenu, count=1)
    return nouveau, nouveau != contenu


def synchroniser_intuition() -> dict:
    """
    Pour chaque position fermée récemment, complète l'entrée intuition_log si elle existait.
    Retourne {"completees": int, "tickers": list[str]}.
    """
    log = _lire_log()
    if not log or "⏳ à remplir" not in log:
        return {"completees": 0, "tickers": []}

    fermees = lire_positions_recentes_fermees(limite=20)
    completees = []
    for p in fermees:
        ticker = p["ticker"]
        if "⏳ à remplir" not in log:
            break
        pnl_pct = p.get("pnl_percent", 0) or 0
        pnl_eur = p.get("pnl_euros", 0) or 0
        nouveau, modifie = _completer_resultat(log, ticker, pnl_pct, pnl_eur)
        if modifie:
            log = nouveau
            completees.append(ticker)

    if completees:
        log = _maj_statistiques(log)
        _ecrire_log(log)
        logger.info(f"Intuition tracker : {len(completees)} entrée(s) complétée(s)")
    return {"completees": len(completees), "tickers": completees}


def _maj_statistiques(contenu: str) -> str:
    """Recalcule et met à jour la section statistiques en haut du fichier."""
    total = len(re.findall(r"\*\*Résultat\*\* : [✅❌]", contenu))
    reussites = len(re.findall(r"\*\*Résultat\*\* : ✅", contenu))
    echecs = total - reussites
    winrate = (reussites / total * 100) if total > 0 else None

    bloc = (f"## Statistiques d'intuition (auto-mises à jour)\n\n"
            f"- Décisions intuitives totales : {total}\n"
            f"- Réussites : {reussites}\n"
            f"- Échecs : {echecs}\n"
            f"- Win rate intuition : {winrate:.1f}%" if winrate is not None else "")

    nouveau = re.sub(
        r"## Statistiques d'intuition.+?(?=\n---)",
        bloc + "\n\n",
        contenu,
        count=1,
        flags=re.DOTALL,
    )
    return nouveau


def stats_intuition() -> dict:
    """Retourne {total, reussites, echecs, winrate_pct}."""
    log = _lire_log()
    total = len(re.findall(r"\*\*Résultat\*\* : [✅❌]", log))
    reussites = len(re.findall(r"\*\*Résultat\*\* : ✅", log))
    return {
        "total":         total,
        "reussites":     reussites,
        "echecs":        total - reussites,
        "winrate_pct":   round(reussites / total * 100, 1) if total > 0 else None,
        "en_attente":    log.count("⏳ à remplir"),
    }
