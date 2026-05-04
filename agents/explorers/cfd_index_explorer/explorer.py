"""
agents/explorers/cfd_index_explorer/explorer.py — CFD Index Explorer
Indices CFD principaux (mappés vers les indices yfinance équivalents).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_volatilite_anormale, filtre_golden_cross, filtre_death_cross,
)

# Mapping CFD → ticker yfinance équivalent (ou futures)
CFD_INDICES = {
    "^GSPC":   "US500 / S&P 500",
    "^IXIC":   "US100 / Nasdaq",
    "^DJI":    "US30 / Dow Jones",
    "^GDAXI":  "DE40 / DAX 40",
    "^FCHI":   "FR40 / CAC 40",
    "^FTSE":   "UK100 / FTSE 100",
    "^N225":   "JP225 / Nikkei 225",
    "^HSI":    "HK50 / Hang Seng",
    "^AXJO":   "AU200 / ASX 200",
    "^IBEX":   "ES35 / IBEX 35",
    "^FTMIB":  "IT40 / FTSE MIB",
    "^STOXX50E": "EU50 / Euro Stoxx 50",
    "^SSMI":   "CH20 / SMI",
    "^AEX":    "NL25 / AEX",
    "^KS11":   "KR200 / KOSPI",
    "^TWII":   "TW50 / TAIEX",
    "^NSEI":   "IN50 / Nifty 50",
    "^TA125.TA": "TA125 / Israel TA",
}


class CFDIndexExplorer(ExplorerBase):
    nom = "cfd_index"

    def universe(self) -> list[str]:
        return list(CFD_INDICES.keys())

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_volatilite_anormale, filtre_golden_cross, filtre_death_cross],
            ticker,
        )
        details = {"prix": float(df["Close"].iloc[-1]), "nom": CFD_INDICES.get(ticker, ticker)}
        return score, raisons, details
