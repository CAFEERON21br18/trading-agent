"""
agents/decision_formatter.py — Formatage markdown du rapport de décision unifié
Rendu lisible en email (markdown standard, pas de bordures unicode).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EMOJI_DECISION = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "NO_TRADE": "⚪"}


def _resume_analyse(nom: str, analyse: dict, poids_pct: int) -> str:
    """Une ligne par sous-agent : direction + confiance + poids + détail court."""
    direction = analyse.get("direction", "N/A")
    confiance = analyse.get("confiance", "?")
    detail    = analyse.get("detail", "") or analyse.get("evaluation", "")
    return f"- **{nom.capitalize()} ({poids_pct}%)** : {direction} {confiance}/10 — {detail}"


def formater_decision(decision: dict, analyses: dict) -> str:
    """
    Génère un bloc markdown pour un actif analysé.
    Args:
        decision : sortie de decision_engine.decider()
        analyses : le dict d'entrée (contient les analyses par sous-agent)
    """
    ticker = decision["ticker"]
    emoji  = EMOJI_DECISION.get(decision["decision"], "")

    # En-tête
    lignes = [
        f"### {emoji} {ticker} — {decision['decision']} ({decision['confidence']}/10)",
        "",
        f"**Score composite** : {decision['score_composite']:+.2f} "
        f"(seuil BUY ≥ +3.0, SELL ≤ −3.0)",
        "",
        "**Synthèse des analyses** :",
    ]
    poids = {"technique": 35, "fondamental": 25, "sentiment": 20, "risque": 20}
    for nom, p in poids.items():
        if nom in analyses:
            lignes.append(_resume_analyse(nom, analyses[nom], p))

    # Convergences
    lignes.append("")
    if decision["convergences"]:
        lignes.append("**✅ Convergences :**")
        for c in decision["convergences"]:
            lignes.append(f"- {c}")
    else:
        lignes.append("**Convergences** : aucune")

    # Contradictions
    lignes.append("")
    if decision["contradictions"]:
        lignes.append("**⚠️ Contradictions :**")
        for c in decision["contradictions"]:
            lignes.append(f"- {c}")
    else:
        lignes.append("**Contradictions** : aucune")

    # Overrides
    lignes.append("")
    if decision["overrides"]:
        lignes.append("**🚫 Overrides :**")
        for o in decision["overrides"]:
            lignes.append(f"- {o}")
    else:
        lignes.append("**Overrides** : aucun")

    # Mémoire
    mem = analyses.get("memory", {})
    perf = mem.get("perf")
    if perf:
        lignes.append("")
        lignes.append(f"**🧠 Mémoire** : winrate {perf['winrate_pct']:.0f}% sur "
                      f"{perf['trades']} trade(s) — P&L moyen {perf['pnl_moyen_pct']:+.2f}%")
    if mem.get("lecons"):
        lignes.append(f"  - Leçons : {len(mem['lecons'])} pertinente(s)")
    if mem.get("patterns"):
        lignes.append(f"  - Patterns connus : {len(mem['patterns'])}")

    # Raisonnement
    lignes.append("")
    lignes.append(f"**Raisonnement** : {decision['reasoning']}")

    # Position (si BUY/SELL et risque validé)
    risk = analyses.get("risque", {})
    if decision["decision"] in ("BUY", "SELL") and risk.get("valide") and risk.get("signal"):
        s = risk["signal"]
        lignes.extend([
            "",
            "**📊 Position recommandée** (paper trading) :",
            f"- Direction       : {'LONG' if decision['decision'] == 'BUY' else 'SHORT'}",
            f"- Prix d'entrée   : {s['prix_entree']:,.4f}",
            f"- Stop-loss       : {s['stop_loss']:,.4f}",
            f"- Target 1 / 2    : {s['target_1']:,.4f} / {s['target_2']:,.4f} (R:R {s['rr_1']:.2f} / {s['rr_2']:.2f})",
            f"- Budget alloué   : {s.get('budget_par_position', 0):.2f}€",
            f"- Taille          : {s['taille_unites']:.6f} unités = {s['montant_investi']:.2f}€",
            f"- Risque réel     : {s['montant_risque_reel']:.2f}€",
        ])

    return "\n".join(lignes)
