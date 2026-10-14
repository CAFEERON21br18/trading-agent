"""
tests/fx_fixtures.py — yfinance simulé pour utils/fx.py : taux inventé (1,25 par défaut), cours
vide, ou erreur de réseau. Aucun appel réseau ; le cache des taux est vidé avant et après.
"""

import contextlib
from unittest import mock

import pandas as pd

from utils import fx

HEURE = pd.Timestamp("2026-10-14 13:30", tz="UTC")  # heure de la dernière bougie simulée


class _Ticker:
    def __init__(self, taux, erreur):
        self.taux, self.erreur = taux, erreur

    def history(self, **kwargs):
        if self.erreur is not None:
            raise self.erreur
        if self.taux is None:
            return pd.DataFrame({"Close": []})
        return pd.DataFrame({"Close": [1.0, self.taux]},
                            index=pd.DatetimeIndex([HEURE - pd.Timedelta(hours=1), HEURE]))


@contextlib.contextmanager
def faux_yfinance(taux=1.25, erreur=None):
    """Rend la liste des tickers demandés à yfinance."""
    appels = []

    def ticker(symbole):
        appels.append(symbole)
        return _Ticker(taux, erreur)

    fx._cache.clear()
    try:
        with mock.patch("yfinance.Ticker", side_effect=ticker):
            yield appels
    finally:
        fx._cache.clear()
