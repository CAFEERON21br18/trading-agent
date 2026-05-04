"""
agents/explorers/forex_explorer/explorer.py — Forex Explorer (paires majeures + croisés + exotiques)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_breakout, filtre_volatilite_anormale,
)
from utils.data_fetcher import FOREX_MAJEURS

# Croisés et quelques exotiques
FOREX_CROISES = {
    "EURGBP=X": "EUR/GBP", "EURJPY=X": "EUR/JPY", "GBPJPY=X": "GBP/JPY",
    "AUDJPY=X": "AUD/JPY", "EURAUD=X": "EUR/AUD",
}
FOREX_EXOTIQUES = {
    "USDTRY=X": "USD/TRY", "USDZAR=X": "USD/ZAR", "USDMXN=X": "USD/MXN",
    "USDBRL=X": "USD/BRL", "USDSGD=X": "USD/SGD", "USDINR=X": "USD/INR",
}


class ForexExplorer(ExplorerBase):
    nom = "forex"

    def universe(self) -> list[str]:
        return list(FOREX_MAJEURS.keys()) + list(FOREX_CROISES.keys()) + list(FOREX_EXOTIQUES.keys())

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_breakout, filtre_volatilite_anormale],
            ticker,
        )
        all_pairs = {**FOREX_MAJEURS, **FOREX_CROISES, **FOREX_EXOTIQUES}
        details = {"prix": float(df["Close"].iloc[-1]), "nom": all_pairs.get(ticker, ticker)}
        return score, raisons, details
