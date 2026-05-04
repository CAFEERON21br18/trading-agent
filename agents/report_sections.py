"""
agents/report_sections.py — Sections enrichies du rapport quotidien
Génère les sections News (via NewsAPI) et Fondamentaux pour les signaux ACHAT/VENTE.
Appelée depuis orchestrator.py.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from agents.analysts.sentiment_analyst.news_fetcher import recuperer_news
from agents.analysts.fundamental_analyst.analyst import analyser_actif as analyser_fondamental

logger = get_logger(__name__)

EMOJI_IMPACT = {"positif": "🟢", "négatif": "🔴", "neutre": "⚪"}


def _signaux_actifs(signaux: list[dict]) -> list[dict]:
    """Filtre les signaux ACHAT / VENTE (ignore les NEUTRE)."""
    return [s for s in signaux if s["signal"] in ("ACHAT", "VENTE")]


def generer_section_news(signaux: list[dict], nb_par_actif: int = 3) -> str:
    """
    Section News — 3 articles max par signal ACHAT/VENTE.
    Consommation NewsAPI : 1 req/signal actif (max ~10/jour sur watchlist).
    """
    actifs = _signaux_actifs(signaux)
    if not actifs:
        return "_Aucun signal actif — pas de news à afficher._"

    blocs = []
    for s in actifs:
        ticker = s["ticker"]
        try:
            news = recuperer_news(ticker, nb_max=nb_par_actif)
        except Exception as e:
            logger.error(f"Erreur news {ticker} : {e}")
            news = []

        entete = f"### {ticker} — {s['signal']} ({s['confiance']}/10)"
        if not news:
            blocs.append(f"{entete}\n_Aucune news disponible._")
            continue

        lignes = [entete]
        for n in news:
            emoji = EMOJI_IMPACT.get(n["impact"], "")
            titre = n["titre"][:120] + "..." if len(n["titre"]) > 120 else n["titre"]
            lignes.append(f"- {emoji} {titre} — _{n['source']}_")
        blocs.append("\n".join(lignes))

    return "\n\n".join(blocs)


def generer_section_fondamentaux(signaux: list[dict]) -> str:
    """
    Section Fondamentaux — analyse fondamentale pour chaque signal ACHAT/VENTE.
    Délègue à analyser_actif() qui dispatche par type (crypto/action/etf).
    Consommation Alpha Vantage : 2 req/action (OVERVIEW + EARNINGS).
    """
    actifs = _signaux_actifs(signaux)
    if not actifs:
        return "_Aucun signal actif — pas d'analyse fondamentale._"

    blocs = []
    for s in actifs:
        try:
            rapport = analyser_fondamental(s["ticker"])
        except Exception as e:
            logger.error(f"Erreur fondamentaux {s['ticker']} : {e}")
            rapport = f"❌ Erreur lors de l'analyse fondamentale de {s['ticker']}"
        blocs.append(f"```\n{rapport}\n```")

    return "\n\n".join(blocs)
