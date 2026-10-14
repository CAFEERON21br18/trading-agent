"""
scripts/migrer_devise_reelle.py — Colonne devise sur real_investments (D1, 14/10/2026).

Migration douce et idempotente :
    ALTER TABLE real_investments ADD COLUMN devise TEXT NOT NULL DEFAULT 'USD'
Les lignes existantes prennent 'USD' : constat du 08/10, les 8 positions réelles
sont saisies en dollars (utils/real_devise.py).

À BLANC PAR DÉFAUT : la base est ouverte en lecture seule et rien n'est écrit ;
le script dit ce qu'il ferait. Avec --appliquer : sauvegarde de la base dans
data/sauvegardes/ (API de sauvegarde SQLite, source en lecture seule), contrôle
de la sauvegarde (intégrité, nombre de lignes), puis ajout de la colonne et
contrôle du résultat. Relancé, il ne fait rien : la colonne est déjà présente.

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\migrer_devise_reelle.py              (à blanc)
    .venv\\Scripts\\python.exe scripts\\migrer_devise_reelle.py --appliquer  (écrit)
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DEFAUT = os.path.join(RACINE, "data", "database.db")
SAUVEGARDES_DEFAUT = os.path.join(RACINE, "data", "sauvegardes")
TABLE, COLONNE, DEFAUT = "real_investments", "devise", "USD"
DDL = f"ALTER TABLE {TABLE} ADD COLUMN {COLONNE} TEXT NOT NULL DEFAULT '{DEFAUT}'"


def _lecture_seule(chemin: str) -> sqlite3.Connection:
    if not os.path.exists(chemin):
        raise FileNotFoundError(chemin)  # mode=ro ne crée jamais de fichier, mais autant le dire
    return sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)


def etat(chemin: str) -> dict:
    """{table, colonne, lignes, integrite}, lus en lecture seule."""
    conn = _lecture_seule(chemin)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})")]
        lignes = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] if cols else 0
        integrite = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    return {"table": bool(cols), "colonne": COLONNE in cols, "lignes": lignes, "integrite": integrite}


def sauvegarder(chemin: str, dossier: str) -> str:
    """Copie cohérente de la base, contrôlée (intégrité, même nombre de lignes) ; rend son chemin."""
    os.makedirs(dossier, exist_ok=True)
    cible = os.path.join(dossier, f"database_avant_devise_{datetime.now():%Y%m%d_%H%M%S}.db")
    if os.path.exists(cible):
        raise FileExistsError(cible)
    src, dst = _lecture_seule(chemin), sqlite3.connect(cible)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    copie, source = etat(cible), etat(chemin)
    if copie["integrite"] != "ok" or copie["lignes"] != source["lignes"] or copie["colonne"]:
        raise RuntimeError(f"sauvegarde non conforme ({cible}) : rien n'a été modifié")
    return cible


def migrer(chemin: str = BASE_DEFAUT, appliquer: bool = False,
           dossier_sauvegarde: str = SAUVEGARDES_DEFAUT) -> dict:
    """{action : « aucune » | « à blanc » | « appliquée », raison, lignes, sauvegarde, controle_ok}."""
    avant = etat(chemin)
    if not avant["table"]:
        return {"action": "aucune", "raison": f"table {TABLE} absente", "lignes": 0}
    if avant["colonne"]:
        return {"action": "aucune", "raison": f"colonne {COLONNE} déjà présente", "lignes": avant["lignes"]}
    if not appliquer:
        return {"action": "à blanc", "lignes": avant["lignes"],
                "raison": f"ajouterait la colonne {COLONNE} ('{DEFAUT}') à {avant['lignes']} ligne(s), "
                          f"après une sauvegarde dans {dossier_sauvegarde}"}
    sauvegarde = sauvegarder(chemin, dossier_sauvegarde)
    conn = sqlite3.connect(chemin, timeout=30)
    try:
        conn.execute(DDL)
        conn.commit()
    finally:
        conn.close()
    apres = etat(chemin)
    conn = _lecture_seule(chemin)
    try:
        autres = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE {COLONNE} IS NOT ?", (DEFAUT,)).fetchone()[0]
    finally:
        conn.close()
    ok = apres["colonne"] and apres["lignes"] == avant["lignes"] and autres == 0 and apres["integrite"] == "ok"
    return {"action": "appliquée", "raison": f"colonne {COLONNE} ajoutée", "lignes": apres["lignes"],
            "sauvegarde": sauvegarde, "controle_ok": ok}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Colonne devise sur real_investments (à blanc par défaut).")
    p.add_argument("--appliquer", action="store_true", help="écrire (sauvegarde d'abord) ; sinon à blanc")
    p.add_argument("--base", default=BASE_DEFAUT, help="base SQLite (défaut : data/database.db)")
    p.add_argument("--sauvegardes", default=SAUVEGARDES_DEFAUT, help="dossier des sauvegardes")
    a = p.parse_args(argv)
    r = migrer(a.base, a.appliquer, a.sauvegardes)
    print(f"{r['action']} : {r['raison']}")
    if r.get("sauvegarde"):
        print(f"sauvegarde : {r['sauvegarde']}")
        print(f"contrôle : {'OK' if r['controle_ok'] else 'ÉCHEC — restaurer la sauvegarde'} "
              f"({r['lignes']} ligne(s))")
    return 0 if r.get("controle_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
