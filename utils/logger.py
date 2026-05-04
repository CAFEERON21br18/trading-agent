"""
utils/logger.py — Module de logging centralisé d'AlphaSignal
Logs structurés avec rotation automatique des fichiers.
Usage : from utils.logger import get_logger; logger = get_logger(__name__)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Dossier des logs (créé si inexistant)
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Format des messages de log
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Fichiers de log par niveau
LOG_FILE_MAIN  = os.path.join(LOGS_DIR, "alphasignal.log")
LOG_FILE_ERROR = os.path.join(LOGS_DIR, "errors.log")


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger configuré pour le module donné.
    Les logs sont écrits dans la console ET dans des fichiers rotatifs.

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
    file_handler = RotatingFileHandler(
        LOG_FILE_MAIN,
        maxBytes=5 * 1024 * 1024,  # 5 Mo
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Handler fichier erreurs — seulement WARNING et plus
    error_handler = RotatingFileHandler(
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
