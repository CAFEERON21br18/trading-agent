"""
agents/explorers/crypto_explorer/explorer.py — Crypto Explorer (top 50 cryptos par market cap)
Hérite de ExplorerBase et spécialise universe() + appliquer_filtres().
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger
from agents.explorers.base import ExplorerBase
from agents.explorers.crypto_explorer.universe import lister_univers, metadata_univers
from agents.explorers.crypto_explorer.screener import evaluer_crypto

logger = get_logger(__name__)


class CryptoExplorer(ExplorerBase):
    """Scanne le top 50 cryptos par market cap (CoinGecko)."""

    nom = "crypto"

    def __init__(self, nb_max: int = 50):
        super().__init__()
        self.nb_max = nb_max
        self._meta = None  # rempli au premier scan

    def universe(self) -> list[str]:
        return lister_univers(self.nb_max)

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        # Charger la metadata une fois pour tout le scan
        if self._meta is None:
            self._meta = metadata_univers(self.nb_max)
        meta = self._meta.get(ticker, {})
        return evaluer_crypto(ticker, meta)


if __name__ == "__main__":
    exp = CryptoExplorer(nb_max=20)
    res = exp.scanner()
    print(f"\n=== Crypto Explorer — résultats ===")
    print(f"Scannés : {res['scannes']}")
    print(f"Découvertes : {len(res['decouvertes'])}")
    for d in res["decouvertes"][:10]:
        print(f"  • {d['ticker']:<10} score {d['score']}/10 — {d['filtres'][:1]}")
