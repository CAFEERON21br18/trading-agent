"""
main.py — Point d'entrée principal d'AlphaSignal
Lance la configuration, initialise les modules, démarre le scheduler.
"""

import sys
import config
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Démarrage principal de l'agent."""
    logger.info("=" * 50)
    logger.info("AlphaSignal — Démarrage")
    logger.info("=" * 50)

    # Afficher et valider la configuration
    config.afficher_config()

    # Vérification du seuil de capital
    if config.CAPITAL <= config.CAPITAL_STOP_THRESHOLD:
        logger.warning(
            f"Capital ({config.CAPITAL}€) sous le seuil d'arrêt "
            f"({config.CAPITAL_STOP_THRESHOLD}€) — signaux suspendus."
        )
        sys.exit(0)

    logger.info("Modules en cours d'initialisation...")
    # TODO Phase 3.2+ : initialiser les sous-agents et lancer le scheduler

    logger.info("AlphaSignal opérationnel.")


if __name__ == "__main__":
    main()
