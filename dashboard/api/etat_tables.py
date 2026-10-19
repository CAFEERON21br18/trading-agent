"""
dashboard/api/etat_tables.py — Dernière ligne écrite et lignes des 24 h, par table (vue temps réel, Phase 3).

LECTURE SEULE : chaque base est ouverte en mode=ro (data/database.db et data/registre.db), délai de
verrou court. Seuls des horodatages, des nombres de lignes et le texte d'une colonne « erreur »
sortent d'ici, jamais d'autre contenu : les tables real_* comptent comme les autres, sans valeur.
- Colonne d'horodatage : la première des COLONNES présente dans la table (la date d'écriture
  avant la date métier : created_at avant timestamp pour prices).
- Valeurs ISO, avec ou sans fuseau ; sans fuseau = UTC (CURRENT_TIMESTAMP de SQLite).
- Colonne « erreur » présente : l'erreur de la dernière ligne est rendue (état « en erreur »).
"""

import os
import sqlite3
from datetime import datetime, timezone

COLONNES = ("horodatage", "created_at", "cree_le", "timestamp", "detected_at", "advice_date",
            "alert_date", "date", "calibrated_at", "last_updated", "closed_at")
DELAI_VERROU_S = 1


def _date(valeur):
    if not isinstance(valeur, str) or len(valeur) < 10:
        return None
    try:
        d = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _borne(exemple: str, depuis: datetime) -> str:
    """Début de fenêtre au format des valeurs de la colonne (comparaison de chaînes en SQL)."""
    d = depuis.astimezone(timezone.utc)
    texte = d.strftime("%Y-%m-%dT%H:%M:%S" if "T" in exemple else "%Y-%m-%d %H:%M:%S")
    return texte + ("+00:00" if exemple.endswith(("+00:00", "Z")) else "")


def _lire_table(conn, table, depuis):
    colonnes = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    col = next((c for c in COLONNES if c in colonnes), None)
    if col is None:
        return {"colonne": None, "derniere": None, "lignes_24h": None, "erreur": None}
    maxi = conn.execute(f'SELECT MAX("{col}") FROM "{table}"').fetchone()[0]
    if maxi is None:
        return {"colonne": col, "derniere": None, "lignes_24h": 0, "erreur": None}
    n = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" >= ?',
                     (_borne(str(maxi), depuis),)).fetchone()[0]
    erreur = passages = None
    if "erreur" in colonnes:
        erreur = conn.execute(f'SELECT erreur FROM "{table}" ORDER BY "{col}" DESC LIMIT 1').fetchone()[0]
    if "passage_id" in colonnes:  # une ligne par décision, plusieurs par passage (registre)
        passages = conn.execute(f'SELECT COUNT(DISTINCT passage_id) FROM "{table}" WHERE "{col}" >= ?',
                                (_borne(str(maxi), depuis),)).fetchone()[0]
    d = _date(str(maxi))
    return {"colonne": col, "derniere": d.isoformat() if d else None, "lignes_24h": n,
            "passages_24h": passages, "erreur": str(erreur)[:300] if erreur not in (None, "") else None}


def lire_tables(bases: dict, tables, depuis: datetime) -> dict:
    """{table: {base, colonne, derniere, lignes_24h, erreur}} pour les tables présentes ; une base
    absente ou illisible est ignorée (ses tables n'ont alors pas de source)."""
    voulues, sortie = set(tables), {}
    for nom_base, chemin in bases.items():
        if not os.path.exists(chemin):
            continue
        try:
            conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=DELAI_VERROU_S)
        except sqlite3.Error:
            continue
        try:
            presentes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for table in sorted((voulues & presentes) - set(sortie)):
                try:
                    sortie[table] = {"base": nom_base, **_lire_table(conn, table, depuis)}
                except sqlite3.Error as e:
                    sortie[table] = {"base": nom_base, "colonne": None, "derniere": None,
                                     "lignes_24h": None, "erreur": None, "illisible": str(e)[:120]}
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return sortie
