"""
agents/rapport_annexes.py — Sections de fin du rapport quotidien, après « Décisions par actif ».

Appelé par agents/orchestrator.generer_rapport_quotidien à l'étape 5, après les décisions, ouvertures,
fermetures et Jev ; ne lève jamais, le rapport et son email partent quand même.
- SECTIONS (TODO §17) : analyse pré-trade condensée (agents/rapport_pretrade.py), News et Fondamentaux
  (agents/report_sections.py), pour les BUY et SELL du cycle. AFFICHAGE seulement ; chacune bornée dans
  le temps, absente si elle échoue ou dépasse son budget (utils/bloc_borne.py).
- Pipeline en mode Prudent (Q2) et registre (R3) : déplacées telles quelles depuis orchestrator.py.
"""

import importlib

from utils.bloc_borne import executer_borne
from utils.logger import get_logger
from utils.registre_ancre import section_registre

logger = get_logger(__name__)

# (nom, module, fonction(decisions) -> str, budget en s)
SECTIONS = [
    ("analyse pré-trade du rapport (TODO §17)", "agents.rapport_pretrade", "section_pretrade", 60),
    ("news du rapport (TODO §17)", "agents.report_sections", "section_news", 60),
    ("fondamentaux du rapport (TODO §17)", "agents.report_sections", "section_fondamentaux", 10),
]


def _lancer(module: str, fonction: str, decisions: list[dict]) -> str:
    return getattr(importlib.import_module(module), fonction)(decisions)


def annexes(decisions: list[dict], cycle_registre: str) -> str:
    """Texte inséré avant le disclaimer du rapport."""
    blocs = []
    for nom, module, fonction, budget in SECTIONS:
        try:
            blocs.append(executer_borne(nom, _lancer, budget, module, fonction, decisions, defaut="") or "")
        except Exception as e:
            logger.warning(f"{nom} : {e}")
    try:  # Phase 4 / Q2 : alerte si trop de fallbacks du pipeline (mode Prudent)
        from agents.skills.pipeline_cache import section_rapport
        bloc_pipeline = section_rapport()
    except Exception as e:
        logger.warning(f"Section pipeline du rapport : {e}")
        bloc_pipeline = ""
    bloc_registre = section_registre(cycle_registre)  # R3 : vérification + ancre de la veille ; ne lève jamais
    return "".join(blocs) + f"{bloc_pipeline}{bloc_registre}"
