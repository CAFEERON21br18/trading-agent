"""
dashboard/pro/jetons.py — Relevés en attente de confirmation, gardés en mémoire du serveur.

Entre l'aperçu d'un relevé et sa confirmation, son contenu n'existe qu'ici : dans la mémoire
du processus, jamais sur le disque, sous un jeton tiré au hasard. Le jeton ne sert qu'une fois
et expire au bout de 10 minutes. Un redémarrage du dashboard vide tout : il suffit de renvoyer
le fichier. Le nombre de relevés en attente est plafonné, pour borner la mémoire.
"""

import secrets
import threading
import time

DUREE_S = 600  # 10 minutes
MAX_EN_ATTENTE = 4  # 4 relevés de 2 Mo au plus ; au-delà, le plus ancien est oublié


class Jetons:
    def __init__(self, horloge=time.monotonic):
        self._horloge = horloge
        self._verrou = threading.Lock()
        self._depots: dict[str, tuple[float, str]] = {}  # jeton -> (expiration, contenu)

    def _purger(self) -> None:
        maintenant = self._horloge()
        for jeton in [j for j, (expire, _) in self._depots.items() if expire <= maintenant]:
            del self._depots[jeton]

    def deposer(self, contenu: str) -> str:
        """Garde le contenu et rend le jeton qui permettra de le reprendre, une seule fois."""
        with self._verrou:
            self._purger()
            while len(self._depots) >= MAX_EN_ATTENTE:
                del self._depots[next(iter(self._depots))]  # le plus ancien
            jeton = secrets.token_urlsafe(32)
            self._depots[jeton] = (self._horloge() + DUREE_S, contenu)
            return jeton

    def retirer(self, jeton: str) -> str | None:
        """Rend le contenu et l'oublie. None si le jeton est inconnu, déjà utilisé ou expiré."""
        with self._verrou:
            self._purger()
            depot = self._depots.pop(jeton, None)
            return None if depot is None else depot[1]

    def __len__(self) -> int:
        with self._verrou:
            self._purger()
            return len(self._depots)


en_attente = Jetons()
