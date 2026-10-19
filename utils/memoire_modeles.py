"""
utils/memoire_modeles.py — Fichiers de memory/ hors du suivi git : modèle au premier lancement.

intuition_log.md, lessons_learned.md, market_patterns.md, trade_journal.md, performance_tracker.md et
metacognition_log.md sont écrits par les cycles et ne sont plus suivis par git (dépôt public). Quand un
écrivain va AJOUTER une entrée à un fichier absent (nouvelle installation), le fichier est d'abord créé
depuis memory/<nom>.exemple (commité), pour garder son en-tête et ses sections. performance_tracker.md
(réécrit en entier) et metacognition_log.md (en-tête créé par agents/skills/_log.py) n'en ont pas besoin.
Un fichier présent n'est jamais touché. Ne lève jamais.
"""

import os
import shutil

MODELES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")


def preparer(chemin: str) -> None:
    """Crée `chemin` depuis le modèle memory/<nom>.exemple s'il est absent et qu'un modèle existe."""
    try:
        modele = os.path.join(MODELES, os.path.basename(chemin) + ".exemple")
        if not os.path.exists(chemin) and os.path.exists(modele):
            os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
            shutil.copyfile(modele, chemin)
    except OSError:
        pass
