"""
agents/explorers/etf_explorer/explorer.py — ETF Explorer (top 50 ETF US par volume)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agents.explorers.base import ExplorerBase
from agents.explorers.screening_helpers import (
    df_avec_indicateurs, appliquer_pack,
    filtre_momentum, filtre_breakout, filtre_volatilite_anormale, filtre_golden_cross,
)

# Univers : ETF populaires couvrant indices larges, sectoriels, thématiques, obligations, refuge
UNIVERS_ETF = [
    # Indices larges
    "SPY", "QQQ", "IWM", "VTI", "VOO", "VXUS",
    # Sectoriels US (XL*)
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLC", "XLRE", "XLU", "XLP", "XLY", "XLB",
    # Thématiques
    "ARKK", "SOXX", "SMH", "BOTZ", "ICLN", "TAN", "LIT", "HACK", "AIQ",
    # Obligations
    "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND",
    # Matières premières / refuge
    "GLD", "SLV", "USO", "DBA",
    # Marchés émergents / régions
    "VWO", "EEM", "FXI", "EWZ", "INDA", "EWJ", "IEUR", "VGK",
    # Leveraged (attention)
    "TQQQ", "SQQQ",
]


class ETFExplorer(ExplorerBase):
    nom = "etf"

    def universe(self) -> list[str]:
        return UNIVERS_ETF

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        df = df_avec_indicateurs(ticker)
        if df.empty:
            return 0, [], {"erreur": "Données indisponibles"}
        score, raisons = appliquer_pack(
            df,
            [filtre_momentum, filtre_breakout, filtre_volatilite_anormale, filtre_golden_cross],
            ticker,
        )
        return score, raisons, {"prix": float(df["Close"].iloc[-1])}
