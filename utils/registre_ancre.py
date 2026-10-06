"""
utils/registre_ancre.py — Ancre quotidienne du registre dans le rapport (Phase 4, R3).

À chaque rapport quotidien : vérification complète de la chaîne d'empreintes, puis ancre de
la veille (jour UTC complet) : nombre de lignes et dernière empreinte jusqu'à ce jour inclus.
L'ancre est écrite une seule fois par jour dans le registre (ligne « ancre ») et recopiée dans
l'email : une copie hors de la machine, qui permet de détecter un historique réécrit.
Ne lève jamais d'exception vers la routine.
"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils import registre

logger = get_logger(__name__)

TITRE = "\n## 🔏 Registre des décisions\n\n"


def _ancre_existante(jour: str) -> dict | None:
    conn = sqlite3.connect(f"file:{registre.CHEMIN}?mode=ro", uri=True)
    try:
        for h, c in conn.execute("SELECT horodatage, contenu FROM registre WHERE type = 'ancre' ORDER BY id"):
            c = json.loads(c)
            if c.get("jour") == jour:
                return {**c, "ecrite_le": h}
    finally:
        conn.close()
    return None


def section_registre(cycle: str = "quotidien") -> str:
    """Section markdown du rapport ; écrit l'ancre de la veille si elle n'existe pas encore."""
    try:
        from scripts.verifier_registre import verifier
        jour = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        r = verifier(registre.CHEMIN, jour)
        if not r["existe"]:
            return TITRE + "Registre absent : aucune ancre.\n"
        a = r["ancre"]
        verif = {"erreurs": len(r["erreurs"]), "passages_non_clos": len(r["passages_non_clos"]),
                 "lignes_total": r["lignes"]}
        if not a["lignes"]:
            return TITRE + f"Aucune ligne jusqu'au {jour} (UTC) : pas d'ancre.\n"
        deja = _ancre_existante(jour)
        if deja is None:
            registre.enregistrer_ancre(cycle, {"jour": jour, **a, "verification": verif})
            logger.info(f"Ancre registre {jour} : {a['lignes']} lignes, empreinte {a['derniere_empreinte'][:16]}")
        lignes = [f"- **Ancre du {jour} (UTC)** : {a['lignes']} lignes ; dernière empreinte :",
                  f"  `{a['derniere_empreinte']}`"]
        if deja is not None:
            lignes.append(f"  (ancre déjà enregistrée le {deja['ecrite_le'][:16].replace('T', ' ')} UTC"
                          + ("" if deja.get("derniere_empreinte") == a["derniere_empreinte"]
                             else " — ❌ **différente de l'état actuel : historique modifié**") + ")")
        if r["erreurs"]:
            lignes.append(f"- **Vérification complète : ❌ {len(r['erreurs'])} anomalie(s)**")
            lignes += [f"  - {e}" for e in r["erreurs"][:5]]
        else:
            lignes.append(f"- **Vérification complète** : ✅ chaîne intègre ({r['lignes']} lignes au total)")
        lignes.append(f"- Passages non clos ou en cours : {len(r['passages_non_clos'])}")
        lignes.append(f"- Contrôle : `python scripts/verifier_registre.py --jour {jour}` doit redonner "
                      "cette empreinte ; une différence signifie que l'historique a été réécrit.")
        return TITRE + "\n".join(lignes) + "\n"
    except Exception as e:
        logger.warning(f"Registre : section du rapport impossible : {e}")
        return TITRE + f"⚠️ Vérification du registre impossible : {str(e)[:160]}\n"
