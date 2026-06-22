"""
agents/skills/pipeline_grouped.py — Pipeline en UN seul appel LLM (v5.4.0).

Remplace les 5 appels du pipeline original par 1 seul appel qui demande
les 5 analyses en JSON. ×5 économie de quota.

Le résultat respecte le contrat de l'ancien pipeline pour ne pas casser
decision_formatter ni decision_engine.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.llm    import ask_llm
from agents.skills._memory_context import (
    contexte_bayesien, contexte_base_rates, contexte_metacognition,
)
from agents.skills._json_helper import parser_json_gemini
from agents.skills._log         import logger_audit

logger = get_logger(__name__)


REASONING_SYSTEM = """Tu es le module de raisonnement d'un agent de trading.
On te donne le contexte d'une décision. Tu produis 5 analyses et tu réponds
UNIQUEMENT en JSON valide (pas de markdown autour), selon ce schéma exact :

{
  "bayesian":     {"prior": <0.0-1.0>, "posterior": <0.0-1.0>, "reasoning": "<2-3 phrases>"},
  "base_rates":   {"verdict": "OK"|"ALERTE", "note": "<comparaison au taux historique>"},
  "second_order": {"verdict": "OK"|"DOUTE", "note": "<conséquence cachée à surveiller>"},
  "premortem":    {"verdict": "OK"|"ALERTE",
                   "dominant_risk": "<risque d'échec principal>",
                   "countermeasures": ["<mesure 1>", "<mesure 2>"]},
  "metacognition":{"verdict": "SOLIDE"|"FRAGILE", "solidity": <1-10>,
                   "bias_detected": "<biais principal détecté ou 'aucun'>"}
}

Contraintes :
- Réponds en français pour les champs textuels.
- Reste FACTUEL : pas d'invention de chiffres absents du contexte.
- Ne propose JAMAIS un buy/sell direct ; tu analyses la décision déjà prise.
- JSON pur, rien autour."""


def doit_executer(decision_result: dict) -> bool:
    """BUY/SELL en style normal uniquement. HOLD/NO_TRADE/learning skippés."""
    return (decision_result.get("decision") in ("BUY", "SELL")
            and decision_result.get("style", "normal") == "normal")


def _resume_analyses(analyses: dict) -> str:
    parts = []
    for nom in ("technique", "fondamental", "sentiment", "risque"):
        a = analyses.get(nom, {})
        if not a:
            continue
        d = a.get("direction", "?"); c = a.get("confiance", "?")
        rsn = a.get("raisonnement") or a.get("rejets") or ""
        if isinstance(rsn, list):
            rsn = " | ".join(rsn)
        parts.append(f"{nom}: {d} ({c}/10) — {str(rsn)[:150]}")
    return "\n".join(parts) or "(aucune analyse)"


def executer_pipeline(ticker: str, analyses: dict, decision_result: dict,
                       regime: str | None = None) -> dict:
    """1 appel LLM au lieu de 5. Contrat de sortie compatible avec l'ancien pipeline."""
    if not doit_executer(decision_result):
        return {"executed": False, "raison": "Pipeline skippé (HOLD/NO_TRADE/learning)"}

    direction = decision_result["decision"]
    score     = decision_result.get("score_composite", 0)
    raison    = decision_result.get("reasoning", "")

    ctx_bay = contexte_bayesien(ticker, regime)
    ctx_br  = contexte_base_rates(ticker, direction)
    ctx_mc  = contexte_metacognition(decision_result)

    prompt = f"""DÉCISION : {direction} sur {ticker}
Score composite : {score:+.2f}  |  Confiance : {decision_result.get('confidence', 0)}/10
Raison rule-based : {raison[:300]}

== HISTORIQUE BAYÉSIEN ==
{ctx_bay['contexte_str']}
Prior suggéré : {ctx_bay['prior']:.2f}

== CLASSE DE RÉFÉRENCE (base rates) ==
{ctx_br['contexte_str']}

== SIGNAUX COMPORTEMENTAUX ==
{ctx_mc['contexte_str']}

== ANALYSES SOUS-AGENTS ==
{_resume_analyses(analyses)}

Produis le JSON des 5 analyses :"""

    res = ask_llm(prompt, system=REASONING_SYSTEM, temperature=0.4,
                   max_tokens=1500, mode="silent")
    if not res.get("text"):
        return {"executed": False, "raison": f"LLM KO : {res.get('error')}",
                "source": None}

    parsed = parser_json_gemini(res["text"])
    if not parsed or "bayesian" not in parsed:
        logger.warning(f"Pipeline {ticker} : parsing JSON échoué")
        return {"executed": False, "raison": "Parsing JSON impossible",
                "source": res.get("source")}

    # Ajustement de taille selon les verdicts critiques
    ajustement, raisons = 1.0, []
    if parsed.get("premortem", {}).get("verdict") == "ALERTE":
        ajustement *= 0.5; raisons.append("Pré-mortem ALERTE (-50%)")
    if parsed.get("metacognition", {}).get("verdict") == "FRAGILE":
        ajustement *= 0.5; raisons.append("Métacognition FRAGILE (-50%)")
    if parsed.get("base_rates", {}).get("verdict") == "ALERTE":
        ajustement *= 0.7; raisons.append("Base rates ALERTE (-30%)")

    # Log métacognition (compat avec _log.py)
    mc = parsed.get("metacognition", {})
    if mc.get("verdict"):
        logger_audit(ticker, direction, {
            "disponible":     True,
            "verdict":        mc.get("verdict", "?"),
            "score_solidite": mc.get("solidity"),
            "biais_detectes": ([{"biais": mc["bias_detected"]}]
                                if mc.get("bias_detected") and mc["bias_detected"] != "aucun"
                                else []),
        })

    # Format de sortie compatible avec decision_formatter (anciennes clés FR)
    return {
        "executed": True,
        "source":   res.get("source"),  # "gemini" ou "groq"
        "bayesien":      {"disponible": True,
                          "prior":         parsed.get("bayesian", {}).get("prior"),
                          "posterior":     parsed.get("bayesian", {}).get("posterior"),
                          "delta":         _delta(parsed.get("bayesian", {})),
                          "raisonnement":  parsed.get("bayesian", {}).get("reasoning", "")},
        "base_rates":    {"disponible": True,
                          "verdict":                 parsed.get("base_rates", {}).get("verdict"),
                          "taux_base":               parsed.get("base_rates", {}).get("note", ""),
                          "biais_individuel_detecte":parsed.get("base_rates", {}).get("note", "")},
        "second_ordre":  {"disponible": True,
                          "verdict_de_decision": parsed.get("second_order", {}).get("verdict"),
                          "angle_a_surveiller":  parsed.get("second_order", {}).get("note", "")},
        "pre_mortem":    {"disponible": True,
                          "verdict":        parsed.get("premortem", {}).get("verdict"),
                          "risque_dominant":parsed.get("premortem", {}).get("dominant_risk", ""),
                          "contre_mesures": parsed.get("premortem", {}).get("countermeasures", [])},
        "metacognition": {"disponible": True,
                          "verdict":         mc.get("verdict"),
                          "score_solidite":  mc.get("solidity"),
                          "biais_detectes":  ([{"biais": mc["bias_detected"]}]
                                              if mc.get("bias_detected") and mc["bias_detected"] != "aucun"
                                              else [])},
        "taille_factor_ajustement": round(ajustement, 2),
        "raisons_ajustement":       raisons,
    }


def _delta(bay: dict) -> float | None:
    """Calcule posterior - prior si les deux sont présents."""
    p, po = bay.get("prior"), bay.get("posterior")
    if isinstance(p, (int, float)) and isinstance(po, (int, float)):
        return round(po - p, 3)
    return None
