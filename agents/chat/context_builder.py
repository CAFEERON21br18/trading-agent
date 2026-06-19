"""
agents/chat/context_builder.py — Assemble le contexte pour répondre à une question
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.helpers import charger_watchlist, tous_les_tickers

logger = get_logger(__name__)


def _extraire_tickers(question: str) -> list[str]:
    """Trouve les tickers mentionnés dans la question."""
    q = question.upper()
    candidats = set()
    try:
        for t in tous_les_tickers(charger_watchlist()):
            base = t.split("-")[0].split("=")[0]
            if base in q or t in q:
                candidats.add(t)
    except Exception:
        pass
    return list(candidats)


def build_context(question: str) -> dict:
    """Rassemble tout le contexte utile pour répondre."""
    context = {"question": question}

    # 1. Paper portfolio
    try:
        from agents.paper_trader.portfolio import etat_portefeuille
        from utils.portfolio_db import lire_positions_ouvertes, lire_positions_recentes_fermees
        context["paper_portfolio"] = etat_portefeuille(with_live_prices=False)
        context["paper_open"] = lire_positions_ouvertes()
        context["paper_recent"] = lire_positions_recentes_fermees(limite=5)
    except Exception as e:
        logger.warning(f"Paper context : {e}")
        context["paper_portfolio"] = {}

    # 2. Real portfolio
    try:
        from utils.real_portfolio_db import resume_portefeuille, lire_investissements, lire_conseils_actifs
        context["real_resume"] = resume_portefeuille()
        context["real_open"] = lire_investissements(filtre_status="OPEN")
        context["real_advice"] = lire_conseils_actifs()
    except Exception as e:
        logger.warning(f"Real context : {e}")
        context["real_resume"] = {}

    # 3. Actifs mentionnés
    tickers = _extraire_tickers(question)
    context["tickers_mentionnes"] = tickers
    context["asset_data"] = {}
    for t in tickers[:3]:
        try:
            from agents.asset_analyzer import analyser_actif_complet
            from agents.decision_engine import decider
            an = analyser_actif_complet(t)
            dc = decider(t, an)
            context["asset_data"][t] = {
                "technique":   an.get("technique"),
                "decision":    dc.get("decision"),
                "confidence":  dc.get("confidence"),
                "score":       dc.get("score_composite"),
                "reasoning":   dc.get("reasoning"),
            }
        except Exception as e:
            logger.warning(f"Asset data {t} : {e}")

    # 4. Performance & mémoire
    try:
        from agents.trade_journalist.intuition_tracker import stats_intuition
        from agents.trade_journalist.performance_tracker import calculer_stats_globales
        context["performance"] = calculer_stats_globales(nb_derniers=20)
        context["intuition"] = stats_intuition()
    except Exception as e:
        logger.warning(f"Memory context : {e}")

    # 5. Knowledge base — concepts pertinents
    try:
        from agents.knowledge.knowledge_base import chercher_concepts
        context["knowledge"] = chercher_concepts(question)
    except Exception:
        context["knowledge"] = []

    # 6. Market context global
    try:
        from agents.analysts.sentiment_analyst.analyst import recuperer_fear_greed_crypto
        context["market_context"] = recuperer_fear_greed_crypto()
    except Exception:
        context["market_context"] = {}

    return context
