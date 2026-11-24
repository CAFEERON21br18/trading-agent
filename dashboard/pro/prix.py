"""
dashboard/pro/prix.py — Dernier prix connu d'un titre, pour valoriser une position ouverte.

Deux sources, dans cet ordre :
1. le dernier cours du grand livre (table cours, remplie par le bouton « Synchroniser ») ;
2. seulement si le grand livre n'a aucun cours pour ce titre, la dernière clôture de la table
   prices de la base de l'agent, ouverte en lecture seule (mode=ro). Aucune autre table de cette
   base n'est lue, ni celles du portefeuille réel ni celles du portefeuille fantôme.
Sans Flask, sans réseau : aucun cours n'est demandé en ligne ici. Un prix absent ou trop vieux ne
vaut jamais 0 : la position est dite « prix indisponible ». L'âge se compte en jours de bourse
(du lundi au vendredi) : un cours du vendredi reste valable le lundi.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import ledger

AGE_MAX_JOURS = 3  # jours de bourse ; au-delà, le prix n'est plus utilisé
GRAND_LIVRE, BASE_AGENT = "grand livre", "base de l'agent"
# Barres retenues dans la base de l'agent : 1 jour, et « 4h » qui contient les barres horaires
# des cryptos. Les barres hebdomadaires sont datées du début de semaine : elles fausseraient l'âge.
REQUETE = ("SELECT close, timestamp FROM prices WHERE ticker = ? AND timeframe IN ('1d', '4h')"
           " AND close IS NOT NULL AND close > 0 ORDER BY timestamp DESC LIMIT 1")


@dataclass(frozen=True)
class Prix:
    valeur: Decimal
    jour: date  # jour du cours utilisé
    origine: str = BASE_AGENT
    devise: str | None = None  # connue pour un cours du grand livre ; sinon devise de cotation


def derniers_prix(chemin_base: str, symboles) -> dict[str, Prix]:
    """Dernière clôture connue de chaque symbole dans la base de l'agent. Un symbole sans prix est
    absent du résultat. Base ou table absente : dictionnaire vide."""
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


def prix_connus(conn, chemin_base: str, symboles) -> dict[str, Prix]:
    """Prix de chaque symbole : le dernier cours du grand livre, et seulement s'il n'y en a aucun,
    le dernier prix de la base de l'agent. conn : grand livre ouvert en lecture, ou None."""
    du_livre: dict[str, Prix] = {}
    for symbole in sorted(set(symboles)):
        cours = ledger.dernier_cours(conn, symbole) if conn is not None else None
        if cours is not None:
            du_livre[symbole] = Prix(cours.cloture, cours.jour, GRAND_LIVRE, cours.devise)
    manquants = [s for s in set(symboles) if s not in du_livre]
    return {**derniers_prix(chemin_base, manquants), **du_livre}


def jours_de_bourse(depuis: date, jusqu_a: date) -> int:
    """Nombre de jours du lundi au vendredi après `depuis`, jusqu'à `jusqu_a` compris. Les jours
    fériés ne sont pas connus : ils comptent comme des jours de bourse."""
    jours, jour = 0, depuis
    while jour < jusqu_a:
        jour += timedelta(days=1)
        jours += jour.weekday() < 5
    return jours


def utilisable(prix: Prix | None, aujourd_hui: date) -> bool:
    """Vrai si le prix existe et que son cours date de 3 jours de bourse au plus."""
    return prix is not None and jours_de_bourse(prix.jour, aujourd_hui) <= AGE_MAX_JOURS
