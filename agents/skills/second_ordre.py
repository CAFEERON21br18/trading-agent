"""
agents/skills/second_ordre.py — Effets de second ordre / conséquences cachées.
Inspiré de Howard Marks : "Et ensuite ?" Au-delà des effets directs,
quelles boucles de rétroaction, conséquences secondaires, réactions des
autres acteurs ?
"""

from utils.gemini import ask_gemini, gemini_disponible
from agents.skills._json_helper import parser_json_gemini, reponse_vide


SYSTEM_PROMPT = """Tu fais une analyse de SECOND ORDRE pour AlphaSignal,
inspirée de Howard Marks.

À partir d'une ACTION ou ÉVÉNEMENT, tu identifies au-delà des effets directs :
- Les effets de 2e ordre (réactions des autres acteurs, boucles)
- Les conséquences cachées (qui passent inaperçues mais comptent)
- Les boucles de rétroaction (auto-renforçantes ou auto-régulatrices)

RÉPONDS EN JSON STRICT :
{
  "effets_directs": ["Le prix monte de X%"],
  "effets_secondaires": [
    {"effet": "Margin calls forcent les leveragés à vendre",
     "delai": "24-48h", "probabilite": "moyenne"}
  ],
  "boucles_retroaction": [
    {"type": "auto-renforçante",
     "description": "Plus le prix monte, plus le FOMO attire de retail"}
  ],
  "consequences_cachees": [
    "Le secteur connexe X profite par ricochet"
  ],
  "verdict_de_decision": "OK | DOUTE | ALERTE",
  "angle_a_surveiller": "Ce qu'il faut watcher en priorité"
}

CONTRAINTES :
- 2-4 effets directs, 2-4 secondaires, 1-3 boucles, 1-3 conséquences cachées
- probabilite ∈ {faible, moyenne, élevée}
- delai en texte court
- boucle.type ∈ {auto-renforçante, auto-régulatrice}
- verdict_de_decision en 1 mot
- Pas de markdown hors JSON."""


def executer(action: str, contexte: str) -> dict:
    """Analyse les effets de second ordre d'une action.

    Args:
        action: l'action/événement analysé ("La Fed baisse les taux de 50bp")
        contexte: contexte de marché / portfolio / secteur

    Returns:
        {"disponible": True, "effets_directs": [...], "effets_secondaires": [...],
         "boucles_retroaction": [...], "consequences_cachees": [...], ...}
    """
    if not gemini_disponible():
        return reponse_vide("Gemini indisponible")
    prompt = (
        f"ACTION / ÉVÉNEMENT : {action}\n\n"
        f"CONTEXTE :\n{contexte}\n\n"
        f"Au-delà des effets directs évidents, donne le JSON de 2e ordre :"
    )
    texte = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.5,
                       max_output_tokens=800)
    data = parser_json_gemini(texte)
    if not data or "effets_secondaires" not in data:
        return reponse_vide("Parsing JSON impossible")
    data["disponible"] = True
    return data
