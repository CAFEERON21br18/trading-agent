"""
agents/skills/pre_mortem.py — Imagine que la décision a échoué dans X mois.
Technique de Klein/Kahneman : visualiser l'échec à l'avance révèle des
risques que l'optimisme initial cache.
"""

from utils.gemini import ask_gemini, gemini_disponible
from agents.skills._json_helper import parser_json_gemini, reponse_vide


SYSTEM_PROMPT = """Tu fais un PRÉ-MORTEM pour AlphaSignal — technique inversée.

Le moteur vient de prendre une décision. Imagine que dans l'HORIZON donné,
cette décision a CLAIREMENT ÉCHOUÉ. Ton rôle :
1. Lister les 3-5 scénarios d'échec les plus plausibles (pas de cas extrêmes
   improbables ; tu cherches les modes d'échec RÉALISTES)
2. Pour chacun, indiquer le signal avant-coureur qui aurait pu l'éviter
3. Proposer 2-3 contre-mesures concrètes (stop, take partial, hedge, attendre)

RÉPONDS EN JSON STRICT :
{
  "scenarios_echec": [
    {
      "scenario": "Earnings miss au prochain trimestre",
      "probabilite": "moyenne",
      "signal_avant_coureur": "Guidance dégradée dans les whispers"
    }
  ],
  "contre_mesures": [
    "Stop loss serré sous 180€",
    "Réduire la taille à 50% si F&G > 75"
  ],
  "risque_dominant": "Le scénario le plus probable est ...",
  "verdict": "OK | DOUTE | ALERTE"
}

CONTRAINTES :
- 3 à 5 scénarios d'échec, chacun avec probabilite ∈ {faible, moyenne, élevée}
- 2 à 4 contre-mesures concrètes (actionnables)
- verdict en 1 mot
- Pas de markdown."""


def executer(decision: str, contexte: str, horizon: str = "3 mois") -> dict:
    """Pré-mortem d'une décision.

    Args:
        decision: ce qu'on s'apprête à faire ("BUY NVDA 50€ stop 180€")
        contexte: le pourquoi + données pertinentes
        horizon: horizon temporel ("1 mois", "3 mois", "fin du trimestre")

    Returns:
        {"disponible": True, "scenarios_echec": [...], "contre_mesures": [...],
         "risque_dominant": "...", "verdict": "OK|DOUTE|ALERTE"}
    """
    if not gemini_disponible():
        return reponse_vide("Gemini indisponible")
    prompt = (
        f"DÉCISION : {decision}\n\n"
        f"CONTEXTE :\n{contexte}\n\n"
        f"HORIZON DE PROJECTION : {horizon}\n\n"
        f"Imagine qu'à la fin de cet horizon, la décision a CLAIREMENT échoué.\n"
        f"Donne ton JSON :"
    )
    texte = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.6,
                       max_output_tokens=700)
    data = parser_json_gemini(texte)
    if not data or "scenarios_echec" not in data:
        return reponse_vide("Parsing JSON impossible")
    data["disponible"] = True
    data["horizon"]    = horizon
    return data
