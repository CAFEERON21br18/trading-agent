"""
agents/decision_engine_meta.py — Métacognition Gemini sur les décisions (v5.3.6).
Audit critique d'une décision après qu'elle ait été prise par le rule-based engine.
N'override JAMAIS la décision — ajoute juste un champ "metacognition" pour traçabilité.
Skippé sur HOLD pur (trop fréquent + peu d'intérêt). Fallback "" si Gemini KO.
Phase 4 / Q1 : désactivé par défaut (config.METACOG_AUDIT_ENABLED) — son
résultat n'est lu par aucun code (docs/TODO.md §6).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.gemini import ask_gemini, gemini_disponible


SYSTEM_PROMPT = """Tu es un AUDITEUR MÉTACOGNITIF pour AlphaSignal.
Le moteur rule-based vient de prendre une décision sur un actif. Ton rôle :
chercher des angles morts, hypothèses cachées, biais et risques que les règles
n'ont pas vus. Tu n'es PAS là pour valider ; tu es là pour stress-tester.

Tu produis 2 à 4 phrases EN FRANÇAIS contenant :
1. Un signal clair "OK" / "DOUTE" / "ALERTE" au début (UN SEUL mot)
2. La principale faiblesse, hypothèse cachée ou scénario adverse identifié
3. Si applicable : quel changement de contexte devrait te faire changer d'avis

INTERDICTIONS STRICTES :
- Ne change JAMAIS la décision (BUY/SELL/HOLD/NO_TRADE) — tu commentes, c'est tout
- Ne donne JAMAIS un nouveau prix, target ou stop
- Pas plus de 4 phrases. Pas de blabla."""


def _resume_analyses(analyses: dict) -> str:
    """Compacte les analyses des sous-agents pour le prompt."""
    parts = []
    for nom in ("technique", "fondamental", "sentiment", "risque"):
        a = analyses.get(nom, {})
        if not a:
            continue
        d   = a.get("direction", "?")
        c   = a.get("confiance", "?")
        rsn = (a.get("raisonnement") or a.get("rejets") or "")
        if isinstance(rsn, list):
            rsn = " | ".join(rsn)
        rsn = str(rsn)[:200]
        parts.append(f"  {nom:12s}: {d} (conf {c}/10) — {rsn}")
    mem = analyses.get("memory", {}).get("perf")
    if mem:
        parts.append(f"  memory      : winrate {mem.get('winrate_pct', 0):.0f}% "
                     f"sur {mem.get('trades', 0)} trades historiques")
    ctx = analyses.get("context", {})
    if ctx.get("fg_valeur") is not None:
        parts.append(f"  fg          : {ctx['fg_valeur']} ({ctx.get('fg_label', '?')})")
    return "\n".join(parts) if parts else "  (analyses non disponibles)"


def audit_metacognitif(ticker: str, decision_result: dict, analyses: dict) -> str:
    """
    Audit critique d'une décision. Retourne une chaîne courte ou "".
    Skippé sur HOLD pur (économie d'appels LLM sur le cas le plus fréquent).
    """
    if not config.METACOG_AUDIT_ENABLED:
        return ""  # Phase 4 / Q1 : aucun appel Gemini (comme origine="chat")
    dec = decision_result.get("decision")
    if dec == "HOLD":
        return ""
    if not gemini_disponible():
        return ""

    score    = decision_result.get("score_composite", 0)
    conf     = decision_result.get("confidence", 0)
    raison   = decision_result.get("reasoning", "")
    convs    = decision_result.get("convergences", [])
    contras  = decision_result.get("contradictions", [])
    overrides = decision_result.get("overrides", [])

    convs_str    = "\n".join(f"  + {c}" for c in convs) or "  (aucune)"
    contras_str  = "\n".join(f"  ⚠️ {c}" for c in contras) or "  (aucune)"
    overrides_str = "\n".join(f"  ⛔ {o}" for o in overrides) or "  (aucun)"

    prompt = f"""ACTIF : {ticker}

DÉCISION DU MOTEUR RULE-BASED :
  decision        : {dec}
  score composite : {score:+.2f}
  confiance       : {conf}/10
  raison          : {raison}

CONVERGENCES :
{convs_str}

CONTRADICTIONS :
{contras_str}

OVERRIDES :
{overrides_str}

ANALYSES BRUTES :
{_resume_analyses(analyses)}

Ton audit (2-4 phrases, début par OK/DOUTE/ALERTE) :"""

    return ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.4,
                      max_output_tokens=350)
