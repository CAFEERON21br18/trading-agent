"""
rejeu/resultat.py — Ce qu'une simulation rend : ses ordres exécutés et la valeur du compte jour
par jour. Objets simples, sans agent ni base, transmissibles d'un processus à l'autre.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

STRATEGIE, REFERENCE_ANNUELLE, REFERENCE_PERIODE = "strategie", "reference_annuelle", "reference_periode"
LIBELLES = {STRATEGIE: "Rejeu", REFERENCE_ANNUELLE: "Référence annuelle", REFERENCE_PERIODE: "Référence période"}


@dataclass(frozen=True)
class Ordre:
    """Un ordre exécuté : une ligne du grand livre du rejeu."""
    ref: str  # référence unique dans le compte (position et côté)
    ticker: str
    quand: datetime
    sens: str  # achat ou vente
    quantite: float
    prix: float
    frais: tuple  # suite de (type, montant Decimal)
    stop: float | None = None  # stop initial, sur l'ordre d'entrée
    statut: str = ""  # sur l'ordre de sortie : CLOSED_SL, CLOSED_TP, CLOSED_REVERSAL, FIN_ANNEE…
    style: str = ""  # normal ou learning (stratégie)


@dataclass
class Resultat:
    """Sortie d'une simulation : la stratégie ou une référence, pour un capital et un profil."""
    nature: str  # STRATEGIE, REFERENCE_ANNUELLE ou REFERENCE_PERIODE
    capital: int
    profil: str
    ordres: list = field(default_factory=list)
    valeurs: list = field(default_factory=list)  # (jour, valeur du compte à la clôture, Decimal)
    decisions: Counter = field(default_factory=Counter)  # (décision, style) -> nombre
    refus: Counter = field(default_factory=Counter)  # motif de refus d'ouverture -> nombre
    erreurs: list = field(default_factory=list)  # erreurs journalisées par l'agent
    ouvertes_a_la_fin: int = 0

    @property
    def compte(self) -> str:
        """Nom du compte dans le grand livre du rejeu."""
        return f"{LIBELLES[self.nature]} {self.capital} EUR {self.profil}"


def nom_compte(nature: str, capital: int, profil: str) -> str:
    return Resultat(nature, capital, profil).compte


def valeur_au(valeurs: list, jour: date) -> Decimal | None:
    """Dernière valeur connue à ce jour ou avant."""
    connue = None
    for j, v in valeurs:
        if j > jour:
            break
        connue = v
    return connue
