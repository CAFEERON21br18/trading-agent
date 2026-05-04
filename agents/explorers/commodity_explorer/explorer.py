"""
agents/explorers/commodity_explorer/explorer.py — Commodity Explorer
Métaux, énergie, agriculture (futures via yfinance =F).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_breakout, filtre_volatilite_anormale,
)
from utils.data_fetcher import COMMODITIES_FUTURES
from agents.analysts.sentiment_analyst.geopolitics import resume_contexte_geopolitique


# Mapping commodity → secteur sensible géopolitique
SENSIBILITE_GEO = {
    "GC=F": "or", "SI=F": "argent", "PL=F": "platine", "PA=F": "palladium",
    "CL=F": "pétrole", "BZ=F": "pétrole", "NG=F": "gaz",
    "HG=F": "cuivre", "ZW=F": "blé", "ZC=F": "maïs", "ZS=F": "soja",
    "KC=F": "café", "CC=F": "cacao", "SB=F": "sucre",
}


class CommodityExplorer(ExplorerBase):
    nom = "commodity"

    def universe(self) -> list[str]:
        return list(COMMODITIES_FUTURES.keys())

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_breakout, filtre_volatilite_anormale],
            ticker,
        )
        # Bonus géopolitique : si l'actif est dans la liste à surveiller
        try:
            ctx = resume_contexte_geopolitique(nb_news=10)
            if ctx.get("actif") and ticker in ctx.get("actifs_a_surveiller", []):
                score = min(10, score + 2)
                raisons.append(f"Actif sensibilisé par contexte géopolitique ({SENSIBILITE_GEO.get(ticker, '?')})")
        except Exception:
            pass
        details = {"prix": float(df["Close"].iloc[-1]),
                   "nom": COMMODITIES_FUTURES.get(ticker, ticker)}
        return score, raisons, details
