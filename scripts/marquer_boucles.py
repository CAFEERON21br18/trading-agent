"""
scripts/marquer_boucles.py — Colonne « boucle » sur les positions paper (REGISTRE_CRITERES v1.8, §9.2).

Définition déterministe (utils/positions_boucles.REQUETE_IDS) : une position est « boucle » si au moins
3 positions de la table ont le même ticker et exactement le même entry_price (valeur stockée, sans
arrondi), toutes dates confondues. Au 19/10/2026 : 16 séries, 313 positions sur 421.

À BLANC PAR DÉFAUT : la base est ouverte en lecture seule, rien n'est écrit, le script affiche ce
qu'il marquerait. Avec --appliquer :
  1. sauvegarde de la base dans data/sauvegardes/ (API de sauvegarde SQLite, source en lecture
     seule), contrôlée (intégrité, même nombre de positions) ;
  2. ajout de la colonne `boucle` (INTEGER, 0 par défaut) si elle manque ;
  3. boucle = 1 pour les positions de la définition, 0 pour les autres ;
  4. contrôle : même nombre de positions, autant de marquées que prévu, intégrité.
Relancé alors que le marquage est à jour, il ne fait rien (ni sauvegarde, ni écriture).

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\marquer_boucles.py              (à blanc)
    .venv\\Scripts\\python.exe scripts\\marquer_boucles.py --appliquer  (écrit)
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from utils.positions_boucles import REQUETE_IDS, REQUETE_SERIES  # noqa: E402

BASE_DEFAUT = os.path.join(RACINE, "data", "database.db")
SAUVEGARDES_DEFAUT = os.path.join(RACINE, "data", "sauvegardes")


def _lecture_seule(chemin: str) -> sqlite3.Connection:
    if not os.path.exists(chemin):
        raise FileNotFoundError(chemin)  # mode=ro ne crée jamais de fichier, mais autant le dire
    return sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)


def etat(chemin: str) -> dict:
    """Positions, séries et ids à marquer, marquage actuel, intégrité ; lus en lecture seule."""
    conn = _lecture_seule(chemin)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(positions)")]
        if not cols:
            return {"table": False}
        a_marquer = {r[0] for r in conn.execute(REQUETE_IDS)}
        series = conn.execute(REQUETE_SERIES + " ORDER BY ticker").fetchall()
        marquees = ({r[0] for r in conn.execute("SELECT id FROM positions WHERE boucle = 1")}
                    if "boucle" in cols else None)
        return {"table": True, "colonne": "boucle" in cols, "a_marquer": a_marquer, "marquees": marquees,
                "series": [(t, n) for t, _, n in series],
                "positions": conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0],
                "integrite": conn.execute("PRAGMA integrity_check").fetchone()[0]}
    finally:
        conn.close()


def sauvegarder(chemin: str, dossier: str) -> str:
    """Copie cohérente de la base, contrôlée (intégrité, même nombre de positions) ; rend son chemin."""
    os.makedirs(dossier, exist_ok=True)
    cible = os.path.join(dossier, f"database_avant_boucles_{datetime.now():%Y%m%d_%H%M%S}.db")
    if os.path.exists(cible):
        raise FileExistsError(cible)
    src, dst = _lecture_seule(chemin), sqlite3.connect(cible)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    copie, source = etat(cible), etat(chemin)
    if copie["integrite"] != "ok" or copie["positions"] != source["positions"]:
        raise RuntimeError(f"sauvegarde non conforme ({cible}) : rien n'a été modifié")
    return cible


def marquer(chemin: str = BASE_DEFAUT, appliquer: bool = False, dossier: str = SAUVEGARDES_DEFAUT) -> dict:
    """{action : « aucune » | « à blanc » | « appliquée », raison, a_marquer, positions, series, ...}."""
    avant = etat(chemin)
    if not avant["table"]:
        return {"action": "aucune", "raison": "table positions absente", "a_marquer": 0, "positions": 0, "series": []}
    n, total = len(avant["a_marquer"]), avant["positions"]
    base = {"a_marquer": n, "positions": total, "series": avant["series"]}
    if avant["colonne"] and avant["marquees"] == avant["a_marquer"]:
        return {**base, "action": "aucune", "raison": f"marquage déjà à jour : {n} position(s) sur {total}"}
    if not appliquer:
        return {**base, "action": "à blanc",
                "raison": f"marquerait {n} position(s) « boucle » sur {total} ({len(avant['series'])} série(s)), "
                          f"après une sauvegarde dans {dossier}"}
    sauvegarde = sauvegarder(chemin, dossier)
    conn = sqlite3.connect(chemin, timeout=30)
    try:
        if not avant["colonne"]:
            conn.execute("ALTER TABLE positions ADD COLUMN boucle INTEGER DEFAULT 0")
        conn.execute(f"UPDATE positions SET boucle = CASE WHEN id IN ({REQUETE_IDS}) THEN 1 ELSE 0 END")
        conn.commit()
    finally:
        conn.close()
    apres = etat(chemin)
    ok = (apres["colonne"] and apres["positions"] == total and apres["marquees"] == avant["a_marquer"]
          and apres["integrite"] == "ok")
    return {**base, "action": "appliquée", "raison": f"{n} position(s) marquée(s) « boucle » sur {total}",
            "sauvegarde": sauvegarde, "controle_ok": ok}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Colonne boucle sur les positions paper (à blanc par défaut).")
    p.add_argument("--appliquer", action="store_true", help="écrire (sauvegarde d'abord) ; sinon à blanc")
    p.add_argument("--base", default=BASE_DEFAUT, help="base SQLite (défaut : data/database.db)")
    p.add_argument("--sauvegardes", default=SAUVEGARDES_DEFAUT, help="dossier des sauvegardes")
    a = p.parse_args(argv)
    r = marquer(a.base, a.appliquer, a.sauvegardes)
    print(f"{r['action']} : {r['raison']}")
    for ticker, n in r.get("series", []):
        print(f"  série {ticker} : {n} position(s)")
    if r.get("sauvegarde"):
        print(f"sauvegarde : {r['sauvegarde']}")
        print(f"contrôle : {'OK' if r['controle_ok'] else 'ÉCHEC — restaurer la sauvegarde'}")
    return 0 if r.get("controle_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
