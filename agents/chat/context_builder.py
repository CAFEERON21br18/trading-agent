"""
agents/chat/context_builder.py — Assemble le contexte pour répondre à une question.
v5.4.2 : le chat récupère les données à la volée pour les actifs hors watchlist.
La logique d'extraction et de fallback yfinance est dans _extraction.py.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from zoneinfo import ZoneInfo

import config
from utils.logger import get_logger
from utils.helpers import charger_watchlist, tous_les_tickers
from agents.chat._extraction import extraire_tickers, get_asset_a_la_volee

logger = get_logger(__name__)


def _heure_locale() -> str:
    """Heure locale du calcul (« 15h20 »), fuseau config.TIMEZONE."""
    try:
        return datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Hh%M")
    except Exception:
        return datetime.now().strftime("%Hh%M")


def _historique_et_reprise(context: dict, question: str, tickers: list) -> list:
    """CHAT_HISTORIQUE=1 : derniers échanges dans context["historique"] ; une question courte
    sans ticker reprend ceux du dernier message utilisateur (context["tickers_herites"]).
    À 0 (défaut) : rien n'est lu, contexte et tickers inchangés."""
    if not config.CHAT_HISTORIQUE:
        return tickers
    from agents.chat import _historique
    try:
        context["historique"] = _historique.lire(question)
    except Exception as e:
        logger.warning(f"Historique du chat : {e}")
        context["historique"] = []
    repris = _historique.tickers_a_reprendre(question, tickers, context["historique"], extraire_tickers)
    if not repris:
        return tickers
    context["tickers_herites"] = True
    return repris


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
    try:  # TODO §8 : P&L latent au dernier prix relevé par les cycles, sans appel réseau
        from agents.chat._pnl_latent import pnl_latent_paper
        context["pnl_latent"] = pnl_latent_paper(context["paper_open"])
    except Exception as e:
        logger.warning(f"P&L latent : {e}")
        context["pnl_latent"] = None
    if context["paper_portfolio"]:  # sans prix, etat_portefeuille met 0 : ce n'est pas un chiffre
        pnl = context["pnl_latent"] or {}
        context["paper_portfolio"]["unrealized_pnl"] = pnl.get("total") if pnl.get("complet") else None

    # 2. Real portfolio
    try:
        from utils.real_portfolio_db import resume_portefeuille, lire_investissements, lire_conseils_actifs
        context["real_resume"] = resume_portefeuille()
        context["real_open"] = lire_investissements(filtre_status="OPEN")
        context["real_advice"] = lire_conseils_actifs()
    except Exception as e:
        logger.warning(f"Real context : {e}")
        context["real_resume"] = {}

    # 3. Actifs mentionnés — v5.4.2 : watchlist OU à la volée (yfinance)
    # Phase 4 / E2 : liste ordonnée (watchlist d'abord) → tickers[:3] déterministe ;
    # decider(origine="chat") : décision technique, sans LLM ni écriture mémoire.
    tickers = _historique_et_reprise(context, question, extraire_tickers(question))
    context["tickers_mentionnes"] = tickers
    context["asset_data"] = {}
    watchlist_set: set[str] = set()
    try:
        watchlist_set = set(tous_les_tickers(charger_watchlist()))
    except Exception:
        pass
    for t in tickers[:3]:
        try:
            if t in watchlist_set:
                from agents.asset_analyzer import analyser_actif_complet
                from agents.decision_engine import decider
                an = analyser_actif_complet(t)
                dc = decider(t, an, origine="chat")
                context["asset_data"][t] = {
                    "in_watchlist": True,
                    "technique":    an.get("technique"),
                    "decision":     dc.get("decision"),
                    "confidence":   dc.get("confidence"),
                    "score":        dc.get("score_composite"),
                    "reasoning":    dc.get("reasoning"),
                    "origine":      "chat",           # calculée à la volée, pas un cycle
                    "calculee_a":   _heure_locale(),
                }
            else:
                data = get_asset_a_la_volee(t)
                context["asset_data"][t] = {"in_watchlist": False, **data}
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
