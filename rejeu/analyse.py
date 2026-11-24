"""
rejeu/analyse.py — Analyse technique de chaque titre, jour par jour, par les VRAIES fonctions de
l'agent : agents.asset_analyzer._technique (tendance et score du Market Analyst),
utils.indicators.calculer_tous_indicateurs et detecter_niveaux_cles (ATR et niveaux que le Risk
Manager relit pour le stop).

Aucun regard vers le futur : pour le jour J, l'agent ne reçoit qu'une VUE des barres coupée à la
clôture de J (analyser_jour ne voit pas le reste de la série). Comme en production, il en lit les
500 dernières (charger_ohlcv, limite=500). Le résultat ne dépend ni du capital ni des frais : il
est calculé une fois et sert aux six configurations.
Les analyses sont indépendantes d'un titre à l'autre : elles sont réparties sur plusieurs
processus (aucun effet sur le résultat, seulement sur la durée).
"""

import logging
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from unittest import mock

import numpy as np
import pandas as pd

from rejeu import parametres as P


@dataclass(frozen=True)
class Analyse:
    """Ce que l'agent calcule d'un titre à la clôture d'un jour."""
    technique: dict  # sortie de agents.asset_analyzer._technique
    atr: float | None  # dernière valeur de l'ATR (None si absente) ; signal non neutre seulement
    niveaux: dict | None  # supports et résistances (detecter_niveaux_cles) ; signal non neutre seulement


def vue_agent(barres: pd.DataFrame) -> pd.DataFrame:
    """Barres au format que charger_ohlcv rend à l'agent : index d'horodatages, colonnes OHLCV."""
    vue = barres.copy()
    vue.index = pd.to_datetime([str(j) for j in barres.index])
    vue.index.name = "timestamp"
    return vue


def analyser_jour(ticker: str, vue: pd.DataFrame) -> Analyse:
    """Analyse à la clôture de la dernière barre de `vue`. `vue` ne contient rien d'après ce jour."""
    from agents import asset_analyzer
    from utils import indicators
    capture = {}

    def indicateurs(df):
        capture["df"] = indicators.calculer_tous_indicateurs(df)
        return capture["df"]

    def charger(_ticker, _timeframe, limite=P.BARRES_SCORE):
        return vue.tail(limite).copy()

    with mock.patch.object(asset_analyzer, "charger_ohlcv", charger), \
            mock.patch.object(asset_analyzer, "calculer_tous_indicateurs", indicateurs):
        technique = asset_analyzer._technique(ticker)
    atr = niveaux = None
    if technique["direction"] in ("ACHAT", "VENTE") and "df" in capture:
        df = capture["df"]
        brut = df["atr"].iloc[-1] if "atr" in df.columns else None
        atr = float(brut) if brut is not None and not np.isnan(brut) else None
        niveaux = indicators.detecter_niveaux_cles(df)
    return Analyse(technique, atr, niveaux)


def analyser_titre(ticker: str, barres: pd.DataFrame, debut=P.DEBUT_REJEU) -> dict:
    """jour -> Analyse, pour chaque barre du titre à partir de `debut`."""
    vue = vue_agent(barres)
    jours = list(barres.index)
    return {jour: analyser_jour(ticker, vue.iloc[:i + 1]) for i, jour in enumerate(jours) if jour >= debut}


def _preparer_processus() -> None:
    for cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
        os.environ.setdefault(cle, "rejeu-sans-email")  # config.py les exige ; aucun e-mail n'est envoyé
    logging.disable(logging.WARNING)  # les journaux de l'agent ne reçoivent que les erreurs


def _tache(argument: tuple) -> tuple:
    ticker, barres, debut = argument
    return ticker, analyser_titre(ticker, barres, debut)


def analyser_univers(barres: dict, processus: int = 1, debut=P.DEBUT_REJEU) -> dict:
    """ticker -> {jour -> Analyse}. processus > 1 : un titre par processus, mêmes résultats."""
    taches = [(t, barres[t], debut) for t in sorted(barres, key=lambda t: -len(barres[t]))]
    if processus <= 1:
        return dict(_tache(t) for t in taches)
    with ProcessPoolExecutor(max_workers=processus, initializer=_preparer_processus) as executeur:
        return dict(executeur.map(_tache, taches))
