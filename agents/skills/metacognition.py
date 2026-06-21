"""
agents/skills/metacognition.py — Audit du raisonnement lui-même.
Version générique (utilisable hors decision_engine). Le module
agents/decision_engine_meta.py est la version spécialisée pour les
décisions de trading.
"""

from utils.gemini import ask_gemini, gemini_disponible
from agents.skills._json_helper import parser_json_gemini, reponse_vide


SYSTEM_PROMPT = """Tu fais de la MÉTACOGNITION pour AlphaSignal — audit du raisonnement.

Tu reçois un RAISONNEMENT (texte ou structure). Ton rôle :
1. Identifier les ANGLES MORTS (ce que le raisonnement ne couvre pas)
2. Repérer les HYPOTHÈSES CACHÉES (admis sans preuve)
3. Détecter les BIAIS COGNITIFS (ancrage, confirmation, récence, etc.)
4. Évaluer la SOLIDITÉ globale du raisonnement
5. Suggérer 1-3 améliorations actionnables

Tu n'es PAS là pour valider. Tu cherches les défauts.

RÉPONDS EN JSON STRICT :
{
  "verdict": "SOLIDE | DOUTEUX | FRAGILE",
  "score_solidite": 7,
  "angles_morts": ["Pas pris en compte la corrélation avec QQQ"],
  "hypotheses_cachees": ["Suppose que le marché reste rationnel"],
  "biais_detectes": [
    {"biais": "biais de confirmation",
     "indice": "Toutes les évidences citées sont 'pour'"}
  ],
  "ameliorations": [
    "Chercher activement 3 évidences contre",
    "Tester la conclusion sur 2 scénarios extrêmes"
  ]
}

CONTRAINTES :
- score_solidite : entier 0-10
- verdict ∈ {SOLIDE, DOUTEUX, FRAGILE}
- 1-3 angles_morts, 1-3 hypotheses_cachees, 0-3 biais_detectes
- 1-3 ameliorations actionnables
- Pas de markdown."""


def executer(raisonnement: str, contexte: str = "") -> dict:
    """Audit métacognitif d'un raisonnement.

    Args:
        raisonnement: le texte du raisonnement à auditer
        contexte: contexte additionnel (faits, données disponibles)

    Returns:
        {"disponible": True, "verdict": "...", "score_solidite": N,
         "angles_morts": [...], "hypotheses_cachees": [...],
         "biais_detectes": [...], "ameliorations": [...]}
    """
    if not gemini_disponible():
        return reponse_vide("Gemini indisponible")
    if not raisonnement or not raisonnement.strip():
        return reponse_vide("Raisonnement vide")
    ctx_str = f"\nCONTEXTE DISPONIBLE :\n{contexte}\n" if contexte else ""
    prompt = (
        f"RAISONNEMENT À AUDITER :\n{raisonnement}\n"
        f"{ctx_str}\n"
        f"Donne ton JSON :"
    )
    texte = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.4,
                       max_output_tokens=700)
    data = parser_json_gemini(texte)
    if not data or "verdict" not in data:
        return reponse_vide("Parsing JSON impossible")
    data["disponible"] = True
    return data
