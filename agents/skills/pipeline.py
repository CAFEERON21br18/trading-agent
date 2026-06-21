"""
agents/skills/pipeline.py — Pipeline de raisonnement avant décision (v5.3.9).
Orchestre les 5 skills de pensée dans l'ordre prévu par le prompt v6.0 :
  1. Bayésien  → probabilité ajustée
  2. Base rates → vue de l'extérieur
  3. Second ordre → conséquences cachées
  4. Pré-mortem → angles d'échec
  5. Métacognition → audit du raisonnement

Auto-skippé sur HOLD, NO_TRADE et trades "learning" (économie quota Gemini).
Coût : 5 appels LLM par décision normale BUY/SELL.
"""

from agents.skills import bayesien, pre_mortem, second_ordre, base_rates, metacognition
from agents.skills._memory_context import (
    contexte_bayesien, contexte_base_rates, contexte_metacognition,
)
from agents.skills._log import logger_audit


def _resume_analyses(analyses: dict) -> str:
    """Compacte les analyses sous-agents pour les prompts."""
    parts = []
    for nom in ("technique", "fondamental", "sentiment", "risque"):
        a = analyses.get(nom, {})
        if not a:
            continue
        d   = a.get("direction", "?")
        c   = a.get("confiance", "?")
        rsn = a.get("raisonnement") or a.get("rejets") or ""
        if isinstance(rsn, list):
            rsn = " | ".join(rsn)
        parts.append(f"{nom}: {d} ({c}/10) — {str(rsn)[:150]}")
    return "\n".join(parts) or "(aucune analyse)"


def doit_executer(decision_result: dict) -> bool:
    """Le pipeline ne tourne que sur BUY/SELL en style normal.
    HOLD, NO_TRADE et learning sont skippés (économie de quota)."""
    dec = decision_result.get("decision")
    style = decision_result.get("style", "normal")
    return dec in ("BUY", "SELL") and style == "normal"


def executer_pipeline(ticker: str, analyses: dict, decision_result: dict,
                       regime: str | None = None) -> dict:
    """Lance les 5 skills en séquence sur une décision actionable.
    Retourne {bayesien, base_rates, second_ordre, pre_mortem, metacognition,
              taille_factor_ajustement, raisons_ajustement, executed: bool}."""
    if not doit_executer(decision_result):
        return {"executed": False, "raison": "Pipeline skippé (HOLD/NO_TRADE/learning)"}

    direction = decision_result["decision"]
    score     = decision_result.get("score_composite", 0)
    raison    = decision_result.get("reasoning", "")

    # ── 1. BAYÉSIEN ─────────────────────────────────────────────────────────
    ctx_bay = contexte_bayesien(ticker, regime)
    hypothese = f"Le trade {direction} sur {ticker} aura un résultat positif"
    # Évidence pour/contre tirée des analyses sous-agents
    evidence_pour, evidence_contre = [], []
    for nom in ("technique", "fondamental", "sentiment"):
        a = analyses.get(nom, {})
        d = (a.get("direction") or "").upper()
        r = str(a.get("raisonnement") or "")[:120]
        if not r:
            continue
        if (direction == "BUY" and d in ("ACHAT", "BULLISH", "POSITIF")) or \
           (direction == "SELL" and d in ("VENTE", "BEARISH", "NEGATIF", "NÉGATIF")):
            evidence_pour.append(f"[{nom}] {r}")
        elif d in ("ACHAT", "BULLISH", "VENTE", "BEARISH"):
            evidence_contre.append(f"[{nom}] {r}")
    bay = bayesien.executer(hypothese, evidence_pour, evidence_contre,
                            prior=ctx_bay["prior"])

    # ── 2. BASE RATES ───────────────────────────────────────────────────────
    ctx_br = contexte_base_rates(ticker, direction)
    br = base_rates.executer(
        question=f"Trader {direction} sur {ticker} est-il sage statistiquement ?",
        contexte=ctx_br["contexte_str"] + "\n\n" + _resume_analyses(analyses),
        classe_reference=ctx_br["classe_ref"],
    )

    # ── 3. SECOND ORDRE ─────────────────────────────────────────────────────
    so = second_ordre.executer(
        action=f"AlphaSignal prend une position {direction} sur {ticker}",
        contexte=_resume_analyses(analyses),
    )

    # ── 4. PRÉ-MORTEM ───────────────────────────────────────────────────────
    pm = pre_mortem.executer(
        decision=f"{direction} {ticker} (score {score:+.2f}, conf {decision_result.get('confidence', 0)}/10)",
        contexte=f"Raison initiale : {raison}\n\n{_resume_analyses(analyses)}",
        horizon="2 mois",
    )

    # ── 5. MÉTACOGNITION ────────────────────────────────────────────────────
    ctx_mc = contexte_metacognition(decision_result)
    raisonnement_combine = (
        f"Décision : {direction} sur {ticker}\n"
        f"Score composite : {score:+.2f}\n"
        f"Raison rule-based : {raison}\n\n"
        f"Analyses :\n{_resume_analyses(analyses)}\n\n"
        f"Signaux comportementaux :\n{ctx_mc['contexte_str']}"
    )
    mc = metacognition.executer(raisonnement_combine, contexte=ctx_mc["contexte_str"])
    logger_audit(ticker, direction, mc)

    # ── Ajustement de la taille si les skills flaggent du critique ──────────
    ajustement = 1.0
    raisons = []
    if pm.get("disponible") and (pm.get("verdict") or "").upper() == "ALERTE":
        ajustement *= 0.5
        raisons.append("Pré-mortem ALERTE (-50%)")
    if mc.get("disponible") and (mc.get("verdict") or "").upper() == "FRAGILE":
        ajustement *= 0.5
        raisons.append("Métacognition FRAGILE (-50%)")
    if br.get("disponible") and (br.get("verdict") or "").upper() == "ALERTE":
        ajustement *= 0.7
        raisons.append("Base rates ALERTE (-30%)")

    return {
        "executed":      True,
        "bayesien":      bay,
        "base_rates":    br,
        "second_ordre":  so,
        "pre_mortem":    pm,
        "metacognition": mc,
        "taille_factor_ajustement": round(ajustement, 2),
        "raisons_ajustement":       raisons,
    }
