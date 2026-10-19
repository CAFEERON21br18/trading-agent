"""
utils/memoire_modeles.py — Fichiers hors du suivi git : modèle au premier lancement.

intuition_log.md, lessons_learned.md, market_patterns.md, trade_journal.md, performance_tracker.md et
metacognition_log.md sont écrits par les cycles et ne sont plus suivis par git (dépôt public). Quand un
écrivain va AJOUTER une entrée à un fichier absent (nouvelle installation), le fichier est d'abord créé
depuis memory/<nom>.exemple (commité), pour garder son en-tête et ses sections. performance_tracker.md
(réécrit en entier) et metacognition_log.md (en-tête créé par agents/skills/_log.py) n'en ont pas besoin.
data/watchlist.json (modifiée depuis le dashboard) est dans le même cas : modèle
data/watchlist.json.exemple, copié par config.py et charger_watchlist() si le fichier manque.
Un fichier présent n'est jamais touché. Ne lève jamais.
"""

import os
import shutil

MODELES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")


def preparer(chemin: str, modele: str | None = None) -> None:
    """Crée `chemin` depuis son modèle s'il est absent et que le modèle existe : `modele` s'il est
    donné, sinon memory/<nom>.exemple."""
    try:
        modele = modele or os.path.join(MODELES, os.path.basename(chemin) + ".exemple")
        if not os.path.exists(chemin) and os.path.exists(modele):
            os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
            shutil.copyfile(modele, chemin)
    except OSError:
        pass
