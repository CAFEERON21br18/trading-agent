"""
agents/explorers/stock_explorer/explorer.py — Stock Explorer (actions mondiales)
V1 : top 50 actions US les plus liquides (rotation possible vers Europe/Asie en V2).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_breakout, filtre_volatilite_anormale,
    filtre_golden_cross,
)

# Top 50 actions US par capitalisation/popularité (V1 — étendre à Europe/Asie en V2)
UNIVERS_US = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "LLY", "AVGO",
    "JPM", "V", "WMT", "XOM", "UNH", "MA", "PG", "JNJ", "HD", "ORCL",
    "COST", "MRK", "ABBV", "BAC", "CVX", "KO", "AMD", "PEP", "ADBE", "CSCO",
    "NFLX", "CRM", "MCD", "TMO", "ACN", "ABT", "WFC", "LIN", "DHR", "TXN",
    "INTC", "DIS", "VZ", "QCOM", "PM", "T", "CMCSA", "INTU", "IBM", "PYPL",
]


class StockExplorer(ExplorerBase):
    nom = "stock"

    def universe(self) -> list[str]:
        return UNIVERS_US

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_breakout, filtre_volatilite_anormale, filtre_golden_cross],
            ticker,
        )
        details = {"prix": float(df["Close"].iloc[-1])}
        return score, raisons, details
