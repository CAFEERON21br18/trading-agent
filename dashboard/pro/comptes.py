"""
dashboard/pro/comptes.py — Les deux comptes affichés, et où lire leurs données.

« Réel (Revolut) » et « Paper (agent) » sont retrouvés par leur nom dans le grand livre : celui
que leur donnent l'import du relevé (importeurs/revolut_csv.py) et la synchronisation paper
(importeurs/paper.py). Chaque compte est lu seul : rien ici n'additionne deux comptes.
Sans Flask. Les chemins sont lus à chaque appel, pour que les tests les remplacent.
"""

import os
import threading
from dataclasses import dataclass

import ledger
from dashboard.pro import donnees
from importeurs import paper, revolut_csv

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEDGER = os.path.join(RACINE, "data", "ledger.db")  # grand livre, hors git
VERROU_ECRITURE = threading.Lock()  # une seule écriture du grand livre à la fois (import, synchronisation)


@dataclass(frozen=True)
class Affiche:
    cle: str  # « reel » ou « paper » : sert aux ancres et aux classes de la page
    nom: str  # nom du compte dans le grand livre
    titre: str


REEL = Affiche("reel", revolut_csv.COMPTE, "Réel (Revolut)")
PAPER = Affiche("paper", paper.COMPTE, "Paper (agent)")
AFFICHES = (REEL, PAPER)


def base_agent() -> str:
    """Chemin de la base de l'agent (cours et positions paper), toujours ouverte en lecture seule ici."""
    from utils import database
    return database.DB_PATH


def source(conn, affiche: Affiche) -> donnees.Source | None:
    """Données du compte, ou None s'il n'existe pas encore dans le grand livre."""
    compte = next((c for c in ledger.comptes(conn) if c.nom == affiche.nom), None)
    return None if compte is None else donnees.charger(conn, compte.id)
