"""
scripts/cleanup.py — Nettoyage hebdomadaire (dimanche 3h)
- Logs > 30 jours → supprimés
- Cache > 7 jours → vidé
- Locks expirés → supprimés
- Vieux rapports daily → archivés (garde 60 jours)
"""

import sys
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.cache import vider as vider_cache, stats as stats_cache
from utils.heartbeat import update_heartbeat

logger = get_logger("cleanup")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOUR_S = 24 * 3600


def _supprimer_fichiers_vieux(dossier: str, max_age_jours: int, ext: str | None = None) -> int:
    """Supprime les fichiers de `dossier` plus anciens que max_age_jours."""
    if not os.path.isdir(dossier):
        return 0
    now = time.time()
    seuil = now - max_age_jours * JOUR_S
    nb = 0
    for f in os.listdir(dossier):
        chemin = os.path.join(dossier, f)
        if not os.path.isfile(chemin):
            continue
        if ext and not f.endswith(ext):
            continue
        if os.path.getmtime(chemin) < seuil:
            try:
                os.remove(chemin)
                nb += 1
            except Exception as e:
                logger.error(f"Suppression {chemin} : {e}")
    return nb


def _purger_locks_expires() -> int:
    """Supprime les fichiers /tmp/alphasignal_*.lock orphelins."""
    nb = 0
    for f in os.listdir("/tmp"):
        if not f.startswith("alphasignal_") or not f.endswith(".lock"):
            continue
        chemin = os.path.join("/tmp", f)
        try:
            age = time.time() - os.path.getmtime(chemin)
            if age > 30 * 60:  # > 30 min
                os.remove(chemin)
                nb += 1
        except Exception as e:
            logger.error(f"Lock {f} : {e}")
    return nb


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("🧹 Cleanup hebdomadaire — démarrage")
    rapport = []

    # Logs > 30j
    n_logs = _supprimer_fichiers_vieux(os.path.join(BASE, "logs"), 30, ext=".log")
    rapport.append(f"  Logs > 30j supprimés : {n_logs}")

    # Rapports daily > 60j
    n_rapports = _supprimer_fichiers_vieux(os.path.join(BASE, "reports", "daily"), 60, ext=".md")
    rapport.append(f"  Rapports daily > 60j supprimés : {n_rapports}")

    # Cache > 7j → on vide tout (rotation propre)
    avant = stats_cache()
    vider_cache()
    rapport.append(f"  Cache vidé (avant : {avant})")

    # Locks expirés
    n_locks = _purger_locks_expires()
    rapport.append(f"  Locks orphelins supprimés : {n_locks}")

    # Reports unsent (ré-essayer plus tard pourrait être utile, on les garde)
    logger.info("\n".join(rapport))
    update_heartbeat("cleanup", status="healthy", duration_sec=_t.time() - t0,
                     extra={"logs_supprimes": n_logs, "rapports_supprimes": n_rapports,
                            "locks_supprimes": n_locks})
    return 0


if __name__ == "__main__":
    sys.exit(main())
