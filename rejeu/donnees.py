"""
rejeu/donnees.py — Barres quotidiennes du rejeu : univers, téléchargement, cache, contrôles.

Univers : les titres de data/watchlist.json.exemple. Barres (ouverture, haut, bas, clôture,
volume) depuis le 01/01/2017, ajustées des divisions d'actions et des dividendes, mises en cache
dans data/rejeu/barres/ (un CSV par titre, hors git). Une fois le cache écrit, il n'est plus
retéléchargé : les relances rejouent exactement les mêmes barres (empreinte dans le rapport).
Le jour en cours n'est jamais gardé : sa barre n'est pas terminée.
Seule telecharger_yfinance va en ligne ; les tests passent une source simulée.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from rejeu import parametres as P

COLONNES = ["Open", "High", "Low", "Close", "Volume"]
PRIX = COLONNES[:4]


@dataclass
class Controle:
    """Ce que les contrôles disent d'un titre. `raisons` non vide : titre écarté du rejeu."""
    ticker: str
    barres: int = 0
    premiere: date | None = None
    derniere: date | None = None
    sans_prix: int = 0  # lignes sans prix rendues par la source, retirées
    doublons: int = 0
    prix_non_positifs: int = 0
    trous: list = field(default_factory=list)  # (dernier jour avant, premier jour après, jours de bourse)
    raisons: list = field(default_factory=list)

    @property
    def utilisable(self) -> bool:
        return not self.raisons


def univers(chemin: str | None = None) -> dict[str, str]:
    """Titre -> catégorie de la liste (crypto, stocks, etf, cfd), dans l'ordre du fichier."""
    with open(chemin or P.UNIVERS, encoding="utf-8") as f:
        liste = json.load(f)
    return {ticker: categorie for categorie, actifs in liste.items() if not categorie.startswith("_")
            for ticker, info in actifs.items() if info.get("actif", True)}


def telecharger_yfinance(ticker: str, debut: date, fin: date) -> pd.DataFrame:
    """Barres quotidiennes ajustées (divisions et dividendes) de debut à fin inclus."""
    import yfinance as yf
    barres = yf.Ticker(ticker).history(start=debut.isoformat(), end=(fin + timedelta(days=1)).isoformat(),
                                       interval="1d", auto_adjust=True, timeout=30)
    if barres is None or barres.empty:
        return pd.DataFrame(columns=COLONNES)
    barres = barres[COLONNES].copy()
    barres.index = pd.Index([h.date() for h in barres.index], name="jour")
    return barres


def chemin_cache(ticker: str, dossier: str | None = None) -> str:
    return os.path.join(dossier or P.DOSSIER, "barres", f"{ticker}.csv")


def jours_de_bourse(depuis: date, jusqu_a: date) -> int:
    """Jours du lundi au vendredi après `depuis`, jusqu'à `jusqu_a` compris."""
    return sum(1 for n in range(1, (jusqu_a - depuis).days + 1) if (depuis + timedelta(days=n)).weekday() < 5)


def controler(ticker: str, brut: pd.DataFrame) -> tuple[pd.DataFrame, Controle]:
    """Nettoie (lignes sans prix retirées, tri par jour) et contrôle. Ne corrige rien d'autre."""
    c = Controle(ticker)
    barres = brut.copy()
    vides = barres[PRIX].isna().any(axis=1)
    c.sans_prix = int(vides.sum())
    barres = barres[~vides].sort_index()
    c.barres = len(barres)
    if c.barres:
        c.premiere, c.derniere = barres.index[0], barres.index[-1]
    c.doublons = int(barres.index.duplicated().sum())
    c.prix_non_positifs = int((barres[PRIX] <= 0).any(axis=1).sum())
    jours = list(barres.index)
    for avant, apres in zip(jours, jours[1:]):
        ecart = jours_de_bourse(avant, apres)
        if ecart > P.TROU_MAX:
            c.trous.append((avant, apres, ecart))
    if c.barres < P.BARRES_MIN:
        c.raisons.append(f"{c.barres} barres, moins de {P.BARRES_MIN}")
    if c.doublons:
        c.raisons.append(f"{c.doublons} date(s) en double")
    if c.prix_non_positifs:
        c.raisons.append(f"{c.prix_non_positifs} barre(s) à prix nul ou négatif")
    if c.trous:
        c.raisons.append(f"{len(c.trous)} trou(s) de plus de {P.TROU_MAX} jours de bourse "
                         f"(le plus long : {max(t[2] for t in c.trous)})")
    return barres, c


def preparer_cache(tickers, telecharger=telecharger_yfinance, aujourd_hui: date | None = None,
                   dossier: str | None = None, rafraichir: bool = False) -> list[str]:
    """Télécharge les titres absents du cache (tous avec rafraichir=True). Rend ceux téléchargés."""
    aujourd_hui = aujourd_hui or date.today()
    faits = []
    for ticker in tickers:
        chemin = chemin_cache(ticker, dossier)
        if os.path.isfile(chemin) and not rafraichir:
            continue
        barres = telecharger(ticker, P.DEBUT_DONNEES, aujourd_hui - timedelta(days=1))
        # jamais la barre du jour en cours
        barres = barres.iloc[[i for i, j in enumerate(barres.index) if j < aujourd_hui]]
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        barres.to_csv(chemin, index_label="jour", lineterminator="\n")
        faits.append(ticker)
    return faits


def charger(tickers, dossier: str | None = None) -> tuple[dict[str, pd.DataFrame], dict[str, Controle]]:
    """Lit le cache. Rend (barres des titres utilisables, contrôles de tous les titres)."""
    barres, controles = {}, {}
    for ticker in tickers:
        chemin = chemin_cache(ticker, dossier)
        if not os.path.isfile(chemin):
            controles[ticker] = Controle(ticker, raisons=["aucune donnée en cache"])
            continue
        brut = pd.read_csv(chemin)
        brut.index = pd.Index([date.fromisoformat(str(j)[:10]) for j in brut.pop("jour")], name="jour")
        propres, controles[ticker] = controler(ticker, brut[COLONNES].astype(float))
        if controles[ticker].utilisable:
            barres[ticker] = propres
    return barres, controles


def empreinte(tickers, dossier: str | None = None) -> str:
    """Empreinte SHA-256 de tout le cache : dit si deux lancements ont rejoué les mêmes barres."""
    h = hashlib.sha256()
    for ticker in sorted(tickers):
        chemin = chemin_cache(ticker, dossier)
        if os.path.isfile(chemin):
            with open(chemin, "rb") as f:
                h.update(ticker.encode() + b"\0" + f.read())
    return h.hexdigest()
