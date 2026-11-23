"""
utils/passage.py — Une ligne INFO « passage » par composant : source d'état de la page Architecture.

Les composants qui ne journalisaient que leurs erreurs (7 explorateurs, queue, Market Analyst, Risk
Manager, Knowledge, Groq) appellent noter_passage(logger, nom) quand ils tournent. La ligne
n'est écrite qu'une fois par processus — un processus de cycle = un passage — puis au plus une fois
toutes les INTERVALLE_S pour les processus longs (dashboard). Format standard de utils/logger : le nom
du logger (module) rattache la ligne au composant (dashboard/api/etat_journaux.py). Rien d'autre ne
change ; la fonction ne lève jamais.
"""

import threading
import time

INTERVALLE_S = 600
_derniers: dict = {}
_verrou = threading.Lock()


def noter_passage(logger, composant: str, detail: str = "") -> None:
    try:
        cle, maintenant = (logger.name, composant), time.monotonic()
        with _verrou:
            if cle in _derniers and maintenant - _derniers[cle] < INTERVALLE_S:
                return
            _derniers[cle] = maintenant
        logger.info(f"{composant} : passage" + (f" ({detail})" if detail else ""))
    except Exception:
        pass
