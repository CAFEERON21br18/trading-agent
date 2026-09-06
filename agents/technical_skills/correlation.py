"""
agents/technical_skills/correlation.py — Skill 4 : corrélation dynamique.

Calcule les corrélations des rendements journaliers entre positions ouvertes
pour détecter la sur-concentration cachée (ex: long BTC + ETH + SOL =
3× le même pari).

Python pur (pandas). Réutilise calculer_correlation() de sentiment_analyst.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger        import get_logger
from utils.portfolio_db  import lire_positions_ouvertes
from agents.analysts.sentiment_analyst.analyst import calculer_correlation

logger = get_logger(__name__)

SEUIL_CORRELATION_HAUTE = 0.7   # au-delà → alerte sur-concentration
SEUIL_CORRELATION_MOYENNE = 0.5


def matrice_correlation(tickers: list[str], jours: int = 60) -> dict:
    """Matrice symétrique {ticker_a: {ticker_b: corr}}. Diagonale = 1.0.
    Corr indispo → None."""
    tickers = list(dict.fromkeys(tickers))  # dédoublonne en préservant l'ordre
    matrice = {t: {} for t in tickers}
    for i, ta in enumerate(tickers):
        matrice[ta][ta] = 1.0
        for tb in tickers[i + 1:]:
            try:
                c = calculer_correlation(ta, tb, jours)
            except Exception as e:
                logger.warning(f"corr {ta}/{tb} : {e}")
                c = None
            matrice[ta][tb] = c
            matrice[tb][ta] = c
    return matrice


def paires_correlees(matrice: dict, seuil: float = SEUIL_CORRELATION_HAUTE) -> list[dict]:
    """Retourne les paires triées par corr décroissante, corr >= seuil."""
    vues = set()
    paires = []
    for ta, ligne in matrice.items():
        for tb, c in ligne.items():
            if ta == tb or c is None:
                continue
            key = tuple(sorted([ta, tb]))
            if key in vues or c < seuil:
                continue
            vues.add(key)
            paires.append({"paire": f"{ta} ↔ {tb}", "correlation": round(c, 3)})
    return sorted(paires, key=lambda p: p["correlation"], reverse=True)


def correlation_portefeuille(jours: int = 60) -> dict:
    """Analyse les positions paper OPEN.
    Retourne {tickers, matrice, paires_hautes, paires_moyennes, alerte}."""
    try:
        positions = lire_positions_ouvertes()
    except Exception as e:
        logger.warning(f"lire_positions_ouvertes : {e}")
        positions = []
    tickers = list(dict.fromkeys(p["ticker"] for p in positions))
    if len(tickers) < 2:
        return {
            "tickers":         tickers,
            "matrice":         {},
            "paires_hautes":   [],
            "paires_moyennes": [],
            "alerte":          None,
        }
    matrice = matrice_correlation(tickers, jours)
    hautes = paires_correlees(matrice, SEUIL_CORRELATION_HAUTE)
    # Moyennes = entre 0.5 et 0.7 (on exclut ce qui est déjà "haute")
    moyennes = [p for p in paires_correlees(matrice, SEUIL_CORRELATION_MOYENNE)
                if p["correlation"] < SEUIL_CORRELATION_HAUTE]
    alerte = None
    if len(hautes) >= 2:
        alerte = (f"⚠️ Sur-concentration : {len(hautes)} paires avec corrélation > "
                  f"{SEUIL_CORRELATION_HAUTE}. Ton portefeuille est moins diversifié "
                  f"qu'il n'y paraît.")
    elif hautes:
        alerte = (f"⚠️ 1 paire avec corrélation > {SEUIL_CORRELATION_HAUTE} : "
                  f"{hautes[0]['paire']} (corr {hautes[0]['correlation']}).")
    return {
        "tickers":         tickers,
        "matrice":         matrice,
        "paires_hautes":   hautes,
        "paires_moyennes": moyennes,
        "alerte":          alerte,
        "seuil_haut":      SEUIL_CORRELATION_HAUTE,
    }


def evaluation_nouvelle_position(candidat: str, jours: int = 60) -> dict:
    """Évalue la corrélation d'un candidat avec les positions ouvertes.
    Retourne {max_corr, avec_qui, warning}."""
    try:
        positions = lire_positions_ouvertes()
    except Exception:
        positions = []
    tickers_ouverts = list(dict.fromkeys(p["ticker"] for p in positions if p["ticker"] != candidat))
    if not tickers_ouverts:
        return {"max_corr": None, "avec_qui": None, "warning": None}
    max_c = None
    avec  = None
    for t in tickers_ouverts:
        c = calculer_correlation(candidat, t, jours)
        if c is None:
            continue
        if max_c is None or c > max_c:
            max_c = c
            avec  = t
    warning = None
    if max_c is not None and max_c >= SEUIL_CORRELATION_HAUTE:
        warning = (f"⚠️ {candidat} est fortement corrélé à {avec} "
                   f"({max_c:.2f}) déjà en portefeuille : sur-concentration cachée.")
    return {
        "max_corr":  round(max_c, 3) if max_c is not None else None,
        "avec_qui":  avec,
        "warning":   warning,
    }
