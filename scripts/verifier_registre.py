"""
scripts/verifier_registre.py — Vérification du registre des décisions (lecture seule, Phase 4, R1).

Contrôle :
- la chaîne d'empreintes : chaque ligne prolonge la précédente (sinon une ligne
  a été supprimée ou insérée) et son empreinte correspond à son contenu
  (sinon elle a été modifiée après écriture) ;
- la présence des trois triggers d'ajout seul ;
- les passages : lignes écrites conformes à la clôture, passages jamais clos.

Usage :
  python scripts/verifier_registre.py                 # base par défaut (data/registre.db)
  python scripts/verifier_registre.py --base fichier.db
  python scripts/verifier_registre.py --jour 2026-10-07   # ancre du jour : nombre de lignes, dernière empreinte
Code de sortie : 0 si tout est conforme, 1 sinon.
"""

import sys
import os
import json
import argparse
import sqlite3
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.registre import CHEMIN, COLONNES, GENESE, empreinte_ligne

TRIGGERS = {"registre_sans_modification", "registre_sans_suppression", "registre_chaine"}


def verifier(chemin: str = CHEMIN, jour: str | None = None) -> dict:
    if not os.path.exists(chemin):
        return {"existe": False, "erreurs": [], "lignes": 0}
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    try:
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        lignes = conn.execute(f"SELECT id, {', '.join(COLONNES)}, hash FROM registre ORDER BY id").fetchall()
    finally:
        conn.close()
    erreurs = [f"trigger absent : {t}" for t in sorted(TRIGGERS - triggers)]
    precedent, par_type, ecrites, clos = GENESE, Counter(), Counter(), {}
    ancre = {"lignes": 0, "derniere_empreinte": None}
    for r in lignes:
        l = dict(zip(("id", *COLONNES, "hash"), r))
        if l["hash_precedent"] != precedent:
            erreurs.append(f"id {l['id']} : maillon rompu (ligne précédente supprimée, insérée ou modifiée)")
        if empreinte_ligne(l) != l["hash"]:
            erreurs.append(f"id {l['id']} : contenu modifié après écriture")
        precedent = l["hash"]
        par_type[l["type"]] += 1
        if l["type"] in ("decision", "reevaluation"):
            ecrites[l["passage_id"]] += 1
        elif l["type"] == "passage":
            clos[l["passage_id"]] = json.loads(l["contenu"])
        if jour and l["horodatage"][:10] <= jour:
            ancre = {"lignes": ancre["lignes"] + 1, "derniere_empreinte": l["hash"]}
    for pid, c in clos.items():
        if c.get("ecrites") != ecrites.get(pid, 0):
            erreurs.append(f"passage {pid} : {ecrites.get(pid, 0)} ligne(s) au registre, {c.get('ecrites')} annoncée(s) à la clôture")
    return {"existe": True, "lignes": len(lignes), "par_type": dict(par_type), "erreurs": erreurs,
            "derniere_empreinte": precedent if lignes else None,
            "passages_non_clos": sorted(set(ecrites) - set(clos)),
            "passages_en_erreur": sum(1 for c in clos.values() if c.get("erreurs")),
            "ancre": ancre if jour else None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie le registre des décisions (lecture seule).")
    parser.add_argument("--base", default=CHEMIN)
    parser.add_argument("--jour", help="AAAA-MM-JJ : ancre (lignes et dernière empreinte jusqu'à ce jour inclus)")
    a = parser.parse_args()
    r = verifier(a.base, a.jour)
    if not r["existe"]:
        print(f"Registre absent : {a.base}")
        return 0
    print(f"{r['lignes']} ligne(s) {r['par_type']} ; dernière empreinte {r['derniere_empreinte']}")
    print(f"Passages non clos : {len(r['passages_non_clos'])} ; passages avec erreurs d'écriture : {r['passages_en_erreur']}")
    if r["ancre"]:
        print(f"Ancre au {a.jour} : {r['ancre']['lignes']} ligne(s), empreinte {r['ancre']['derniere_empreinte']}")
    for e in r["erreurs"]:
        print(f"  ❌ {e}")
    print("✅ Registre intègre" if not r["erreurs"] else f"❌ {len(r['erreurs'])} anomalie(s)")
    return 1 if r["erreurs"] else 0


if __name__ == "__main__":
    sys.exit(main())
