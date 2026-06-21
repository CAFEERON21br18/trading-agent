"""
agents/skills/base_rates.py — Référence aux taux de base.
Kahneman : la plupart des biais viennent de l'ignorance des taux de base.
Avant de juger un cas individuel, demande-toi : qu'arrive-t-il EN MOYENNE
dans cette classe de situations ?
"""

from utils.gemini import ask_gemini, gemini_disponible
from agents.skills._json_helper import parser_json_gemini, reponse_vide


SYSTEM_PROMPT = """Tu invoques les BASE RATES (Kahneman) pour AlphaSignal.

À partir d'une QUESTION ou CAS INDIVIDUEL, tu :
1. Identifies la CLASSE DE RÉFÉRENCE pertinente (population de cas comparables)
2. Donnes le TAUX DE BASE historique de cette classe (chiffres, ordres de grandeur)
3. Identifies en quoi le cas étudié pourrait DÉVIER du taux de base
4. Estimes la prévision finale en mélangeant taux de base + ajustement
5. Flag si l'optimisme/pessimisme dévie trop des base rates sans justification

RÉPONDS EN JSON STRICT :
{
  "classe_reference": "Actions tech avec P/E > 50 sur 24 mois",
  "taux_base": "Sous-performent l'indice 65% du temps sur 24 mois",
  "specificites_du_cas": [
    "Vertiv a un moat AI infra (positif vs classe)",
    "Mais valorisation à 4σ au-dessus de la moyenne historique"
  ],
  "prevision_ajustee": "55% de probabilité de sous-performance",
  "biais_individuel_detecte": "narrative AI surchauffée — risque optimisme",
  "verdict": "OK | DOUTE | ALERTE"
}

CONTRAINTES :
- classe_reference doit être précise (pas "actions" mais "actions tech à forte croissance post-IPO")
- taux_base avec un chiffre ou ordre de grandeur si possible
- 2 à 4 specificites_du_cas
- biais_individuel_detecte : le piège mental le plus probable
- verdict en 1 mot
- Pas de markdown."""


def executer(question: str, contexte: str = "",
             classe_reference: str | None = None) -> dict:
    """Analyse via taux de base.

    Args:
        question: question ou hypothèse étudiée
        contexte: données pertinentes sur le cas individuel
        classe_reference: forcer la classe (sinon Gemini la choisit)

    Returns:
        {"disponible": True, "classe_reference": "...", "taux_base": "...",
         "specificites_du_cas": [...], "prevision_ajustee": "...",
         "biais_individuel_detecte": "...", "verdict": "..."}
    """
    if not gemini_disponible():
        return reponse_vide("Gemini indisponible")
    classe_str = (f"\nCLASSE DE RÉFÉRENCE IMPOSÉE : {classe_reference}\n"
                  if classe_reference else "")
    prompt = (
        f"QUESTION / CAS : {question}\n\n"
        f"CONTEXTE : {contexte or '(aucun)'}\n"
        f"{classe_str}\n"
        f"Donne ton JSON :"
    )
    texte = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.4,
                       max_output_tokens=600)
    data = parser_json_gemini(texte)
    if not data or "taux_base" not in data:
        return reponse_vide("Parsing JSON impossible")
    data["disponible"] = True
    return data
