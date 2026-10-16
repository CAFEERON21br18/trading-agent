"""
utils/logger.py — Module de logging centralisé d'AlphaSignal
Un fichier par tâche (TODO §1) : logs/<tâche>.log (tous niveaux) et logs/<tâche>_errors.log
(WARNING et plus), avec rotation. La tâche se déduit du script lancé (nom_tache) :
scripts/cycle_tactical.py → tactical, dashboard/app.py → dashboard, scripts/cleanup.py → cleanup.
Les cycles et le dashboard n'ouvrent donc jamais le même fichier : sous Windows, la rotation d'un
fichier commun ouvert par un autre processus échouait (WinError 32) à chaque ligne.
Usage : from utils.logger import get_logger; logger = get_logger(__name__)
"""

import logging
import os
import re
import sys

from utils.journal_rotation import RotationTolerante

# Dossier des logs (créé si inexistant)
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Format des messages de log
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def nom_tache(script: str | None = None) -> str:
    """Nom de la tâche, tiré du script lancé (sys.argv[0] par défaut) : cycle_<x>.py → <x> ;
    dashboard/app.py → dashboard ; python -m <paquet> → <paquet> ; autre script → son nom ;
    python -c ou console → python."""
    chemin = (sys.argv[0] if sys.argv else "") if script is None else script
    if not chemin or chemin.startswith("-"):
        return "python"
    base = os.path.splitext(os.path.basename(chemin))[0]
    parent = os.path.basename(os.path.dirname(os.path.abspath(chemin)))
    if base == "__main__":
        base = parent
    elif base == "app" and parent == "dashboard":
        base = "dashboard"
    if base.startswith("cycle_"):
        base = base[len("cycle_"):]
    return re.sub(r"[^A-Za-z0-9_-]", "_", base).strip("_-") or "python"


def fichiers_de(tache: str) -> tuple[str, str]:
    """(fichier principal, fichier des erreurs) d'une tâche."""
    return os.path.join(LOGS_DIR, f"{tache}.log"), os.path.join(LOGS_DIR, f"{tache}_errors.log")


# Fichiers du processus, relus à chaque get_logger (le banc et les tests les redirigent)
TACHE = nom_tache()
LOG_FILE_MAIN, LOG_FILE_ERROR = fichiers_de(TACHE)


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger configuré pour le module donné.
    Les logs sont écrits dans la console ET dans les fichiers rotatifs de la tâche.

    Args:
        name: Nom du module (utiliser __name__ en général)

    Returns:
        Logger configuré
    """
    logger = logging.getLogger(name)

    # Éviter les doublons si le logger est déjà configuré
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Handler console — affiche INFO et plus
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Handler fichier principal — tous les niveaux, rotation à 5 Mo, garde 5 fichiers
    file_handler = RotationTolerante(
        LOG_FILE_MAIN,
        maxBytes=5 * 1024 * 1024,  # 5 Mo
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Handler fichier erreurs — seulement WARNING et plus
    error_handler = RotationTolerante(
        LOG_FILE_ERROR,
        maxBytes=2 * 1024 * 1024,  # 2 Mo
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    return logger
