"""
scripts/nettoyer_signaux_test.py — Purge les signaux de test de la BDD
⚠️  À lancer UNIQUEMENT avant la mise en production.
Efface tous les signaux SIG-0001 à SIG-0005 et leurs résultats associés.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_connection
from utils.logger   import get_logger

logger = get_logger(__name__)

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL_FILE = os.path.join(BASE_DIR, "memory", "trade_journal.md")


def purger_signaux_test():
    """Supprime tous les signaux en BDD et repart de zéro."""
    confirmation = input("⚠️  Supprimer TOUS les signaux en BDD ? (taper 'OUI' pour confirmer) : ")
    if confirmation != "OUI":
        print("Annulé.")
        return

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM signal_results")
    cursor.execute("DELETE FROM signals")
    conn.commit()
    conn.close()

    # Réinitialisation du journal markdown (garder le header, supprimer les entrées)
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            f.write("""# AlphaSignal — Journal de Trading

> Enregistrement de tous les signaux émis et leurs résultats.
> Ne jamais supprimer d'entrées — seulement ajouter.

---

## Statistiques globales

| Métrique | Valeur |
|----------|--------|
| Total signaux | 0 |
| Dernier signal | — |

---
""")
    except Exception as e:
        logger.error(f"Erreur réinitialisation journal : {e}")

    print("✅ BDD et journal purgés. Tu peux démarrer en production.")


if __name__ == "__main__":
    purger_signaux_test()
