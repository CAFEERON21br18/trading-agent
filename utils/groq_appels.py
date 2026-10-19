"""
utils/groq_appels.py — Groq vu par la carte de l'agent (Phase 3) : une ligne INFO par passage.

Les appels Groq restent dans utils/llm.py (routeur Gemini → Groq, inchangé). Ce module note seulement
qu'un appel a eu lieu, sous le logger « utils.groq_appels », que la page Architecture rattache au composant
Groq (dashboard/api/topology_composants.py : utils/groq → llm.groq), comme utils/gemini.py pour Gemini.
"""

from utils.logger import get_logger
from utils.passage import noter_passage

logger = get_logger(__name__)


def noter_appel(modele: str, ok: bool) -> None:
    noter_passage(logger, "Groq", f"modèle {modele}, appel {'réussi' if ok else 'en échec'}")
