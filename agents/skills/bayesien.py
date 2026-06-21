"""
agents/skills/bayesien.py — Révision bayésienne d'une hypothèse.
Donne un prior + évidences pour/contre → estime un posterior + raisonnement.
"""

from utils.gemini import ask_gemini, gemini_disponible
from agents.skills._json_helper import parser_json_gemini, reponse_vide


SYSTEM_PROMPT = """Tu es un raisonneur bayésien rigoureux pour AlphaSignal.

À partir d'une HYPOTHÈSE, d'un PRIOR (probabilité initiale) et de listes
d'évidences POUR et CONTRE, tu produis un raisonnement bayésien structuré :
- Identifie le poids relatif (faible / moyen / fort) de chaque évidence
- Combine-les pour estimer un POSTERIOR (probabilité révisée)
- Justifie en français en 3-4 phrases courtes

RÉPONDS EXCLUSIVEMENT EN JSON STRICT, format :
{
  "posterior": 0.62,
  "delta": +0.12,
  "raisonnement": "Le prior de 0.5 est révisé à la hausse car ...",
  "facteurs_decisifs": ["RSI 25 (poids fort)", "earnings beat (poids moyen)"],
  "incertitude": "moyenne"
}

CONTRAINTES :
- posterior et delta sont des nombres entre 0 et 1 (et -1 et +1 pour delta)
- raisonnement = 3-4 phrases max
- facteurs_decisifs = top 2-4 évidences (pour ou contre)
- incertitude ∈ {faible, moyenne, élevée}
- Pas de markdown, pas de texte hors JSON."""


def executer(hypothese: str, evidence_pour: list[str], evidence_contre: list[str],
             prior: float = 0.5) -> dict:
    """Révise une hypothèse à la lumière de l'évidence.

    Args:
        hypothese: l'affirmation testée ("NVDA va dépasser 200$ d'ici 1 mois")
        evidence_pour: liste d'éléments soutenant l'hypothèse
        evidence_contre: liste d'éléments contredisant l'hypothèse
        prior: probabilité initiale (0..1), défaut 0.5

    Returns:
        {"disponible": True, "posterior": 0.6, "delta": +0.1, ...}
        ou {"disponible": False, ...} si Gemini KO.
    """
    if not gemini_disponible():
        return reponse_vide("Gemini indisponible")
    prior = max(0.01, min(0.99, float(prior)))
    pour_str   = "\n".join(f"- {e}" for e in evidence_pour) or "(aucune)"
    contre_str = "\n".join(f"- {e}" for e in evidence_contre) or "(aucune)"
    prompt = (
        f"HYPOTHÈSE : {hypothese}\n\n"
        f"PRIOR : {prior}\n\n"
        f"ÉVIDENCE POUR :\n{pour_str}\n\n"
        f"ÉVIDENCE CONTRE :\n{contre_str}\n\n"
        f"Ton JSON :"
    )
    texte = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.3,
                       max_output_tokens=500)
    data = parser_json_gemini(texte)
    if not data or "posterior" not in data:
        return reponse_vide("Parsing JSON impossible")
    data["disponible"] = True
    data["prior"]      = prior
    return data
