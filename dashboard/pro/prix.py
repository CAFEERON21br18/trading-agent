"""
dashboard/pro/prix.py — Dernier prix connu d'un titre, lu dans la base de l'agent.

Base ouverte en lecture seule (mode=ro) ; seule la table prices est lue, jamais une table du
portefeuille réel ni du portefeuille fantôme. Sans Flask, sans réseau : aucun cours n'est demandé en ligne.
Un prix absent ou trop vieux ne vaut jamais 0 : la position est dite « prix indisponible ».
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

AGE_MAX_JOURS = 3  # au-delà, le prix n'est plus utilisé (consigne du 24/11/2026)
# Barres retenues : 1 jour, et « 4h » qui contient les barres horaires des cryptos.
# Les barres hebdomadaires sont datées du début de semaine : elles fausseraient l'âge du prix.
REQUETE = ("SELECT close, timestamp FROM prices WHERE ticker = ? AND timeframe IN ('1d', '4h')"
           " AND close IS NOT NULL AND close > 0 ORDER BY timestamp DESC LIMIT 1")


@dataclass(frozen=True)
class Prix:
    valeur: Decimal
    jour: date  # jour de la barre


def derniers_prix(chemin_base: str, symboles) -> dict[str, Prix]:
    """Dernière clôture connue de chaque symbole. Un symbole sans prix est absent du résultat.

    Base ou table absente : dictionnaire vide, donc tout est « prix indisponible ».
    """
    if not os.path.isfile(chemin_base):
        return {}
    trouves: dict[str, Prix] = {}
    conn = sqlite3.connect(Path(chemin_base).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for symbole in sorted(set(symboles)):
            ligne = conn.execute(REQUETE, (symbole,)).fetchone()
            if ligne is None:
                continue
            try:
                trouves[symbole] = Prix(Decimal(str(ligne[0])), date.fromisoformat(str(ligne[1])[:10]))
            except (ValueError, ArithmeticError):
                continue  # barre illisible : prix indisponible
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return trouves


def utilisable(prix: Prix | None, aujourd_hui: date) -> bool:
    """Vrai si le prix existe et que sa barre date de 3 jours au plus (jours calendaires)."""
    return prix is not None and (aujourd_hui - prix.jour).days <= AGE_MAX_JOURS
