"""
agents/decision_engine.py — Moteur de décision unifié d'AlphaSignal
Reçoit les analyses des sous-agents, les croise, détecte convergences/contradictions,
vérifie les overrides et la mémoire, produit UNE décision argumentée.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.audit_trace import zone_audit
from agents.decision_regles import (  # noqa: F401 — réexport
    POIDS, SEUIL_BUY, SEUIL_SELL, SEUIL_LEARNING, SEUIL_CONTRADICTION, WINRATE_PRUDENCE,
    TAILLE_LEARNING_PCT, TAILLE_CONTRADICTION,
    _direction_a_signe, _normaliser, _convergences_contradictions, _verifier_overrides,
)

logger = get_logger(__name__)


@zone_audit("decision_engine")  # audit du chat (Phase 4) : no-op hors requête auditée
def decider(ticker: str, analyses: dict, origine: str = "cycle") -> dict:
    """
    Entrée principale du Decision Engine — 5 étapes (v4) :
      1. Collecter & normaliser
      2. Corréler (convergences / contradictions)
      3. Vérifier les overrides
      4. Consulter l'intuition (mémoire + contexte)
      5. Décider et logger
    origine="chat" (Phase 4 / E2) : décision technique seule, voir plus bas.
    """
    scores      = _normaliser(analyses)
    score_total = round(sum(scores.values()), 2)
    convergences, contradictions = _convergences_contradictions(analyses)
    overrides   = _verifier_overrides(ticker, analyses)

    style, taille_factor = "normal", 1.0  # style de trading et facteur de taille (v4.1)

    # ── Décision préliminaire (v4.1 — contradictions ne bloquent plus) ───────
    if overrides:
        decision = "NO_TRADE"
        raison   = f"Override actif : {overrides[0]}"
    elif score_total >= SEUIL_BUY:
        decision = "BUY"
        raison   = f"Score composite +{score_total} ≥ {SEUIL_BUY}, signaux cohérents"
    elif score_total <= SEUIL_SELL:
        decision = "SELL"
        raison   = f"Score composite {score_total} ≤ {SEUIL_SELL}, signaux baissiers"
    elif score_total >= SEUIL_LEARNING:
        # Trade d'apprentissage — micro-position
        decision = "BUY"
        style    = "learning"
        taille_factor = TAILLE_LEARNING_PCT
        raison   = f"Score composite +{score_total} faible — trade d'apprentissage (micro-position)"
    elif score_total <= -SEUIL_LEARNING:
        decision = "SELL"
        style    = "learning"
        taille_factor = TAILLE_LEARNING_PCT
        raison   = f"Score composite {score_total} faible — trade d'apprentissage short (micro-position)"
    else:
        decision = "HOLD"
        raison   = f"Score composite {score_total} dans la zone neutre — pas d'avantage détecté"

    # Contradictions : ne bloquent plus, mais réduisent la taille
    if contradictions and decision in ("BUY", "SELL"):
        taille_factor *= TAILLE_CONTRADICTION
        raison += f" | ⚠️ Taille -{int((1 - TAILLE_CONTRADICTION) * 100)}% à cause d'une contradiction"

    # ── Étape 4 — Consulter l'intuition (peut override la décision) ──────────
    from agents.intuition import consulter_intuition, journaliser_intuition
    intuition = consulter_intuition(ticker, analyses, decision)
    if intuition.get("override_decision"):
        ancienne = decision
        decision = intuition["override_decision"]
        if decision in ("BUY", "SELL") and ancienne in ("HOLD", "NO_TRADE"):
            style = "learning"  # override intuitif → micro-position pour prudence
            taille_factor = TAILLE_LEARNING_PCT
        raison = f"Intuition override ({ancienne} → {decision}) : {intuition['raisons'][0]}"

    # ── Confiance finale (avec boost intuition) ──────────────────────────────
    conf_max = max(float(analyses.get(k, {}).get("confiance", 0) or 0) for k in POIDS)
    conf_finale = min(10, conf_max + len(convergences) + intuition.get("boost_confiance", 0))
    if decision == "NO_TRADE":
        conf_finale = max(1, int(conf_max))

    resultat = {
        "ticker":           ticker,
        "decision":         decision,
        "style":            style,           # "normal" | "learning"
        "taille_factor":    taille_factor,   # 1.0 (normal), 0.5 (contradiction), 0.2 (learning)
        "confidence":       int(conf_finale),
        "score_composite":  score_total,
        "scores_detail":    scores,
        "reasoning":        raison,
        "convergences":     convergences,
        "contradictions":   contradictions,
        "overrides":        overrides,
        "intuition":        intuition,
    }
    journaliser_intuition(ticker, resultat, intuition, origine)  # journal seulement : rien n'est lu en retour

    # v5.5.2 — Score de qualité du setup (Skill technique 3)
    try:
        from agents.technical_skills.setup_quality import noter_setup
        qual = noter_setup(analyses, resultat)
        resultat["quality_grade"]     = qual["grade"]
        resultat["quality_score"]     = qual["score"]
        resultat["quality_criteres"]  = qual["criteres"]
    except Exception as e:
        logger.warning(f"Setup quality {ticker} : {e}")
        resultat["quality_grade"] = "?"

    # Phase 4 / E2 — origine="chat" : ni audit métacognitif ni pipeline (aucun
    # appel LLM, aucune écriture dans metacognition_log). Cycles : inchangés.
    if origine == "chat":
        resultat.update(origine="chat", metacognition="", pipeline_raisonnement={
            "executed": False, "raison": "origine=chat : non exécuté"})
        return resultat

    # v5.3.6 — Audit métacognitif Gemini (n'override pas, juste annote)
    try:
        from agents.decision_engine_meta import audit_metacognitif
        resultat["metacognition"] = audit_metacognitif(ticker, resultat, analyses)
    except Exception as e:
        logger.warning(f"Métacognition {ticker} : {e}")
        resultat["metacognition"] = ""

    # v5.4.0 — Pipeline GROUPÉ (1 appel LLM au lieu de 5) sur BUY/SELL normaux
    # Phase 4 / Q2 : une analyse par actif, action et jour (cache), sinon mode Prudent
    try:
        from agents.skills.pipeline_cache import executer_pipeline_cache
        regime = analyses.get("context", {}).get("regime_marche")
        pipeline = executer_pipeline_cache(ticker, analyses, resultat, regime=regime, origine=origine)
        resultat["pipeline_raisonnement"] = pipeline
        if ((pipeline.get("executed") or pipeline.get("fallback"))
                and pipeline.get("taille_factor_ajustement", 1.0) < 1.0):
            ancien = resultat["taille_factor"]
            resultat["taille_factor"] = round(ancien * pipeline["taille_factor_ajustement"], 2)
            logger.info(f"Taille {ticker} ajustée par pipeline : "
                        f"{ancien:.2f} → {resultat['taille_factor']:.2f} "
                        f"({', '.join(pipeline['raisons_ajustement'])})")
    except Exception as e:
        logger.warning(f"Pipeline raisonnement {ticker} : {e}")
        resultat["pipeline_raisonnement"] = {"executed": False, "raison": str(e)[:200]}
    return resultat


def reevaluer_position(position: dict, analyses: dict) -> dict:
    """
    v4.1 — Réévalue une position ouverte avec une analyse fraîche.
    Décide si on garde, ferme, ou ajuste. Appelé par cycle_tactical toutes les 15 min.

    Retourne :
      {"action": "GARDER" | "CLOSE", "raison": str}
    """
    direction_pos = position["direction"]  # "LONG" ou "SHORT"
    technique = analyses.get("technique", {})
    sig_tech = _direction_a_signe(technique.get("direction", "NEUTRE"))
    conf_tech = float(technique.get("confiance", 0) or 0)

    # 1. Signal technique inverse fort → fermer
    if direction_pos == "LONG" and sig_tech < 0 and conf_tech >= 7:
        return {"action": "CLOSE",
                "raison": f"Signal technique inverse fort ({technique['direction']} {conf_tech:.0f}/10)"}
    if direction_pos == "SHORT" and sig_tech > 0 and conf_tech >= 7:
        return {"action": "CLOSE",
                "raison": f"Signal technique inverse fort ({technique['direction']} {conf_tech:.0f}/10)"}

    # 2. Override géopolitique critique → fermer
    overrides = _verifier_overrides(position["ticker"], analyses)
    if overrides:
        return {"action": "CLOSE",
                "raison": f"Override critique : {overrides[0]}"}

    # 3. Position vieille de 30+ jours sans progrès — V1 simple : on ne calcule pas l'âge
    # (à affiner en V2 — comparer entry_date vs maintenant)

    return {"action": "GARDER", "raison": "Conditions stables"}
