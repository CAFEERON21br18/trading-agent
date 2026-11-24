"""
tests/rejeu_fixtures.py — Barres fabriquées pour les tests du rejeu (rejeu/).

Séries de prix inventées, dont le résultat se calcule à la main ; dossier temporaire, jamais
data/ ; aucun réseau (une source simulée rend les barres). Tickers de la vraie liste (AAPL,
BTC-USD…) pour que les règles de l'agent les classent, avec des cours qui ne sont pas les leurs.
"""

from datetime import date, timedelta

import pandas as pd

from rejeu import donnees


def jours_ouvres(debut: date, n: int) -> list[date]:
    """n jours du lundi au vendredi à partir de debut."""
    jours, jour = [], debut
    while len(jours) < n:
        if jour.weekday() < 5:
            jours.append(jour)
        jour += timedelta(days=1)
    return jours


def barres(jours: list[date], clotures: list[float], ecart: float = 0.01, ouvertures=None) -> pd.DataFrame:
    """Barres dont l'ouverture vaut la clôture de la veille (ou `ouvertures`), avec un haut et un
    bas à ±ecart autour du corps de la bougie."""
    lignes = []
    for i, (jour, cloture) in enumerate(zip(jours, clotures)):
        ouverture = ouvertures[i] if ouvertures else (clotures[i - 1] if i else cloture)
        haut, bas = max(ouverture, cloture) * (1 + ecart), min(ouverture, cloture) * (1 - ecart)
        lignes.append((ouverture, haut, bas, cloture, 1_000_000.0))
    return pd.DataFrame(lignes, columns=donnees.COLONNES, index=pd.Index(jours, name="jour"))


def source(par_ticker: dict):
    """Source simulée : rend les barres fabriquées du titre, tronquées à la période demandée."""
    appels = []

    def telecharger(ticker, debut, fin):
        appels.append((ticker, debut, fin))
        df = par_ticker.get(ticker)
        if df is None:
            return pd.DataFrame(columns=donnees.COLONNES)
        return df.iloc[[i for i, j in enumerate(df.index) if debut <= j <= fin]]
    telecharger.appels = appels
    return telecharger
