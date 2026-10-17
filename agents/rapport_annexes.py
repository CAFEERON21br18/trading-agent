"""
agents/rapport_annexes.py — Sections de fin du rapport quotidien, après « Décisions par actif ».

Appelé par agents/orchestrator.generer_rapport_quotidien à l'étape 5, après les décisions, ouvertures,
fermetures et Jev ; ne lève jamais, le rapport et son email partent quand même.
- Analyse pré-trade condensée des BUY et SELL du cycle (TODO §17, agents/rapport_pretrade.py) :
  AFFICHAGE seulement, bornée dans le temps, "" si elle échoue (utils/bloc_borne.py).
- Pipeline en mode Prudent (Q2) et registre (R3) : déplacées telles quelles depuis orchestrator.py.
"""

from utils.bloc_borne import executer_borne
from utils.logger import get_logger
from utils.registre_ancre import section_registre

logger = get_logger(__name__)

BUDGET_PRETRADE_S = 60


def _pretrade(decisions: list[dict]) -> str:
    from agents.rapport_pretrade import section_pretrade
    return section_pretrade(decisions)


def annexes(decisions: list[dict], cycle_registre: str) -> str:
    """Texte inséré avant le disclaimer du rapport."""
    bloc_pretrade = executer_borne("analyse pré-trade du rapport (TODO §17)", _pretrade, BUDGET_PRETRADE_S,
                                   decisions, defaut="") or ""
    try:  # Phase 4 / Q2 : alerte si trop de fallbacks du pipeline (mode Prudent)
        from agents.skills.pipeline_cache import section_rapport
        bloc_pipeline = section_rapport()
    except Exception as e:
        logger.warning(f"Section pipeline du rapport : {e}")
        bloc_pipeline = ""
    bloc_registre = section_registre(cycle_registre)  # R3 : vérification + ancre de la veille ; ne lève jamais
    return f"{bloc_pretrade}{bloc_pipeline}{bloc_registre}"
