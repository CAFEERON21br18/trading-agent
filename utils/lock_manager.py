"""
utils/lock_manager.py — Système de lock entre les 5 cycles d'exécution
Évite que 2 cycles tournent en même temps et créent des races sur la BDD.

Hiérarchie d'exclusion :
- CRITIQUE  : ne vérifie jamais (toujours prioritaire)
- TACTIQUE  : skip si STRATÉGIQUE ou QUOTIDIEN tourne
- STRATÉGIQUE : skip si QUOTIDIEN tourne
- QUOTIDIEN/HEBDO : peuvent skip si l'autre tourne

Lock auto-expiré après 30 min (protection crash).
"""

import os
import sys
import json
import time
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

# Portabilité Windows/macOS/Linux : "/tmp" en dur n'existe pas sous Windows
# (os.path.join("/tmp", ...) produit "/tmp\\..." qui n'est ni un chemin
# absolu Windows valide ni un dossier existant). tempfile.gettempdir()
# retourne le dossier temp correct sur chaque OS (respecte TEMP/TMP sous
# Windows, TMPDIR sous macOS/Linux) sans dépendre de l'existence de /tmp.
#
# Remarque sur les verrous orphelins : contrairement à /tmp sous Unix
# (souvent vidé au démarrage), le dossier temp Windows n'est PAS purgé au
# redémarrage — un verrou laissé par un arrêt brutal peut donc survivre
# indéfiniment. C'est déjà géré indépendamment de l'OS par l'expiration
# basée sur l'âge du fichier (EXPIRATION_S) dans est_actif() : un verrou
# plus vieux que 30 min est considéré orphelin et supprimé, que le dossier
# temp ait été nettoyé par l'OS ou non.
LOCK_DIR     = tempfile.gettempdir()
LOCK_PREFIX  = "alphasignal_"
EXPIRATION_S = 30 * 60  # 30 minutes


class LockAcquisitionError(OSError):
    """Échec réel de création du fichier de lock (I/O, permissions...).

    À distinguer explicitement du cas « verrou déjà détenu » (qui renvoie
    False) : une erreur de création est une panne d'infrastructure, pas
    une situation normale de contention entre cycles. La confondre avec
    « déjà acquis » masquerait une panne réelle (cf. logs Windows où le
    dossier /tmp était introuvable).
    """


def _chemin_lock(cycle: str) -> str:
    return os.path.join(LOCK_DIR, f"{LOCK_PREFIX}{cycle}.lock")


def acquerir_lock(cycle: str) -> bool:
    """
    Crée un lock file pour le cycle. Retourne True si acquis, False si un
    verrou valide est déjà détenu par un autre cycle (situation normale).

    En cas d'échec de création du verrou pour une raison technique
    (dossier temp inaccessible, permissions, disque plein...), lève
    LockAcquisitionError plutôt que de renvoyer False : ce n'est pas la
    même situation qu'un verrou déjà détenu et ne doit pas être journalisée
    comme telle par les appelants.

    Le lock est auto-libéré si > 30 min (protection crash / verrou orphelin).
    """
    chemin = _chemin_lock(cycle)
    if est_actif(cycle):
        logger.info(f"Lock {cycle} déjà actif — abandon")
        return False
    try:
        with open(chemin, "w") as f:
            json.dump({"cycle": cycle, "pid": os.getpid(),
                       "acquired_at": datetime.now(timezone.utc).isoformat()}, f)
        logger.info(f"Lock {cycle} acquis (pid {os.getpid()})")
        return True
    except OSError as e:
        logger.error(f"Erreur de création du lock {cycle} (panne, pas une contention) : {e}")
        raise LockAcquisitionError(f"Impossible de créer le lock {cycle} : {e}") from e


def liberer_lock(cycle: str) -> None:
    """Libère le lock du cycle (à la fin de l'exécution)."""
    chemin = _chemin_lock(cycle)
    try:
        if os.path.exists(chemin):
            os.remove(chemin)
            logger.info(f"Lock {cycle} libéré")
    except Exception as e:
        logger.error(f"Erreur libération lock {cycle} : {e}")


def est_actif(cycle: str) -> bool:
    """Retourne True si un lock existe et n'est pas expiré."""
    chemin = _chemin_lock(cycle)
    if not os.path.exists(chemin):
        return False
    try:
        age = time.time() - os.path.getmtime(chemin)
        if age > EXPIRATION_S:
            logger.warning(f"Lock {cycle} expiré (âge {age:.0f}s) — suppression")
            os.remove(chemin)
            return False
        return True
    except Exception as e:
        logger.error(f"Erreur vérification lock {cycle} : {e}")
        return False


def doit_skipper(cycle_courant: str) -> tuple[bool, str]:
    """
    Vérifie la hiérarchie d'exclusion. Retourne (skip, raison).
    """
    hierarchie = {
        "critical":  [],
        "tactical":  ["strategic", "daily", "weekly"],
        "strategic": ["daily", "weekly"],
        "daily":     ["weekly"],
        "weekly":    ["daily"],
    }
    bloqueurs = hierarchie.get(cycle_courant, [])
    for c in bloqueurs:
        if est_actif(c):
            return True, f"Cycle {c} en cours — {cycle_courant} skippé"
    return False, ""


def cycles_actifs() -> list[str]:
    """Liste des cycles actuellement actifs (non expirés)."""
    actifs = []
    for c in ("critical", "tactical", "strategic", "daily", "weekly"):
        if est_actif(c):
            actifs.append(c)
    return actifs
