"""
agents/skills/_json_helper.py — Parsing tolérant des réponses Gemini en JSON.
Les skills demandent un JSON strict, mais Gemini peut renvoyer du texte
avec un bloc ```json … ```. On extrait et on parse.
"""

import json
import re


def parser_json_gemini(texte: str) -> dict | None:
    """Extrait et parse un JSON depuis une réponse Gemini.
    Tolère : JSON pur, ```json … ```, texte avant/après le bloc.
    Retourne None si rien d'exploitable."""
    if not texte:
        return None

    # 1. JSON pur en premier essai
    try:
        return json.loads(texte)
    except Exception:
        pass

    # 2. Bloc ```json … ```
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", texte, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 3. Premier { … } ou [ … ] complet
    match = re.search(r"(\{.*\}|\[.*\])", texte, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None


def reponse_vide(motif: str = "Skill indisponible") -> dict:
    """Retour standard quand Gemini KO ou parsing impossible."""
    return {"disponible": False, "raison": motif}
