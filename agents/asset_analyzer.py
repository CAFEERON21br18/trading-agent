"""
agents/asset_analyzer.py — Collecte de toutes les analyses pour un actif
Appelle technique, fondamental, sentiment, risk, memory et retourne un dict
prêt pour le Decision Engine.
"""

import sys
import os
import re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.logger import get_logger
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs
from agents.analysts.market_analyst.analyst import calculer_score, analyser_tendance
from agents.analysts.fundamental_analyst.analyst import analyser_actif as analyser_fondamental_texte
from agents.analysts.sentiment_analyst.news_fetcher import recuperer_news
from agents.analysts.risk_manager.manager import valider_signal
from agents.memory_reader import consulter_memoire

logger = get_logger(__name__)


def _technique(ticker: str) -> dict:
    """Extrait signal technique sous forme {direction, confiance, prix, motifs, detail}."""
    df = charger_ohlcv(ticker, "1d", limite=500)
    if df.empty:
        return {"direction": "NEUTRE", "confiance": 0, "prix": None, "motifs": [], "detail": "Données absentes"}
    df = calculer_tous_indicateurs(df)
    if "rsi" not in df.columns:
        return {"direction": "NEUTRE", "confiance": 0, "prix": None, "motifs": [], "detail": "Indicateurs non calculables"}
    tendance, _ = analyser_tendance(df)
    score, signal, motifs = calculer_score(df, tendance)
    return {
        "direction": signal,
        "confiance": score,
        "prix":      float(df["Close"].iloc[-1]),
        "tendance":  tendance,
        "motifs":    motifs,
        "detail":    motifs[0] if motifs else f"Tendance {tendance}",
    }


def _parser_fondamental(rapport_texte: str) -> dict:
    """Extrait direction/confiance/évaluation du texte produit par analyser_actif."""
    if rapport_texte.startswith("❌"):
        return {"direction": "NEUTRE", "confiance": 0, "evaluation": "Données indisponibles", "detail": rapport_texte}
    eval_m = re.search(r"Évaluation\s*:\s*([^\n]+)", rapport_texte)
    impact_m = re.search(r"Impact attendu\s*:\s*([^\n]+)", rapport_texte)
    conf_m = re.search(r"Confiance\s*:\s*(\d+)", rapport_texte)
    evaluation = eval_m.group(1).strip() if eval_m else "N/A"
    impact     = impact_m.group(1).strip() if impact_m else "Neutre"
    confiance  = int(conf_m.group(1)) if conf_m else 0
    direction = {"Positif": "POSITIF", "Négatif": "NÉGATIF"}.get(impact, "NEUTRE")
    return {"direction": direction, "confiance": confiance, "evaluation": evaluation, "detail": evaluation}


def _fondamental(ticker: str) -> dict:
    try:
        rapport = analyser_fondamental_texte(ticker)
        return _parser_fondamental(rapport)
    except Exception as e:
        logger.error(f"Fondamental {ticker} : {e}")
        return {"direction": "NEUTRE", "confiance": 0, "evaluation": "Erreur", "detail": str(e)[:80]}


def _sentiment(ticker: str, nb_news: int = 5) -> dict:
    """Agrège les news : majorité positif/négatif → direction. Confiance = nb articles pertinents."""
    try:
        news = recuperer_news(ticker, nb_max=nb_news)
    except Exception as e:
        logger.error(f"Sentiment {ticker} : {e}")
        return {"direction": "NEUTRE", "confiance": 0, "narratif": "News indisponibles", "detail": "Erreur"}
    if not news:
        return {"direction": "NEUTRE", "confiance": 0, "narratif": "Aucune news", "detail": "0 article"}
    impacts = Counter(n["impact"] for n in news)
    pos, neg, neu = impacts.get("positif", 0), impacts.get("négatif", 0), impacts.get("neutre", 0)
    total = pos + neg + neu
    if pos > neg + 1:
        direction, conf = "POSITIF", min(10, 4 + pos)
    elif neg > pos + 1:
        direction, conf = "NÉGATIF", min(10, 4 + neg)
    else:
        direction, conf = "NEUTRE", min(5, total)
    detail = f"{pos}+ / {neg}- / {neu}~ ({total} articles)"
    return {"direction": direction, "confiance": conf, "narratif": detail, "detail": detail}


def _risque(ticker: str, technique: dict, cash_disponible: float | None, nb_positions: int) -> dict:
    """Appelle Risk Manager seulement si signal non-neutre, sinon retourne valide=True placeholder."""
    if technique["direction"] not in ("ACHAT", "VENTE") or technique["prix"] is None:
        return {"valide": True, "rejets": [], "avertissements": [], "signal": None, "direction": "NEUTRE", "confiance": 0}
    direction = "LONG" if technique["direction"] == "ACHAT" else "SHORT"
    try:
        r = valider_signal(ticker, direction, technique["prix"],
                           cash_disponible=cash_disponible,
                           nb_positions_visees=nb_positions)
        # On garde les clés existantes + on ajoute direction/confiance pour le scoring
        r["direction"] = "ACHAT" if direction == "LONG" else "VENTE"
        r["confiance"] = 0  # le risque ne contribue pas en score (poids 20% mais 0 par défaut)
        return r
    except Exception as e:
        logger.error(f"Risque {ticker} : {e}")
        return {"valide": False, "rejets": [str(e)[:120]], "avertissements": [], "signal": None,
                "direction": "NEUTRE", "confiance": 0}


def analyser_actif_complet(ticker: str, sentiment_global: dict | None = None,
                           cash_disponible: float | None = None,
                           nb_positions_visees: int = 1) -> dict:
    """Collecte technique + fondamental + sentiment + risque + mémoire pour un actif."""
    technique  = _technique(ticker)
    fondamental = _fondamental(ticker)
    sentiment  = _sentiment(ticker)
    risque     = _risque(ticker, technique, cash_disponible, nb_positions_visees)
    memory     = consulter_memoire(ticker)
    context = dict(sentiment_global or {})
    # v5.5.0 — Régime de marché courant pour cet actif + global (Skill 1)
    try:
        from agents.technical_skills.market_regime import dernier_regime
        r_actif = dernier_regime(ticker)
        r_glob  = dernier_regime("global")
        if r_actif:
            context["regime_marche"] = r_actif.get("regime")
            context["regime_adx"]    = r_actif.get("adx")
        if r_glob:
            context["regime_global"] = r_glob.get("regime")
    except Exception:
        pass
    return {
        "technique":   technique,
        "fondamental": fondamental,
        "sentiment":   sentiment,
        "risque":      risque,
        "memory":      memory,
        "context":     context,
    }
