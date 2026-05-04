"""
agents/explorers/index_explorer/explorer.py — Index Explorer (indices mondiaux)
Univers : INDICES_MONDIAUX du data_fetcher (S&P, CAC, DAX, Nikkei, etc.).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_volatilite_anormale, filtre_golden_cross, filtre_death_cross,
)
from utils.data_fetcher import INDICES_MONDIAUX


class IndexExplorer(ExplorerBase):
    nom = "index"

    def universe(self) -> list[str]:
        return list(INDICES_MONDIAUX.keys())

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        # Pour les indices : focus sur cross EMA + volatilité (pas de breakout volume bruyant)
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_volatilite_anormale, filtre_golden_cross, filtre_death_cross],
            ticker,
        )
        details = {"prix": float(df["Close"].iloc[-1]),
                   "nom": INDICES_MONDIAUX.get(ticker, ticker)}
        return score, raisons, details
