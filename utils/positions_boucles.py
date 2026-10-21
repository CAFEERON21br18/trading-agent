"""
utils/positions_boucles.py — Positions paper « boucle » (REGISTRE_CRITERES v1.8, §9.2 et §9.5).

- Définition déterministe (§9.2) : une position est « boucle » si au moins 3 positions de la table,
  elle comprise, ont le même ticker et exactement le même entry_price (valeur REAL stockée, sans
  arrondi), toutes dates confondues. REQUETE_IDS la reproduit ; scripts/marquer_boucles.py
  l'écrit dans la colonne `boucle` de `positions`.
- Statistiques paper (§9.5) : fermees_recentes() remplace lire_positions_recentes_fermees() pour
  les modes du Budget Manager, les écritures de lessons_learned / market_patterns et, depuis la
  v1.9, la porte paper défensive et le suivi d'intuition. Interrupteur
  EXCLURE_BOUCLES_STATS à 0 (jusqu'au 28/10/2026), ou colonne absente : résultat identique à
  lire_positions_recentes_fermees(). À 1 : les positions marquées « boucle » sont exclues.
- memory_lookups et performance_tracker lisent signals / signal_results, qui n'ont aucun lien avec
  `positions` : rien à exclure chez eux tant que signal_results n'est pas alimentée par les positions.
"""

import os
import sqlite3

import config
from utils import database, portfolio_db
from utils.logger import get_logger

logger = get_logger(__name__)

REQUETE_SERIES = ("SELECT ticker, entry_price, COUNT(*) AS n FROM positions "
                  "GROUP BY ticker, entry_price HAVING COUNT(*) >= 3")
REQUETE_IDS = ("SELECT id FROM positions WHERE (ticker, entry_price) IN "
               "(SELECT ticker, entry_price FROM positions GROUP BY ticker, entry_price HAVING COUNT(*) >= 3)")


def exclusion_active() -> bool:
    return bool(getattr(config, "EXCLURE_BOUCLES_STATS", 0))


def colonne_presente(conn) -> bool:
    return "boucle" in {r[1] for r in conn.execute("PRAGMA table_info(positions)")}


def fermees_recentes(limite: int = 10) -> list[dict]:
    """Positions fermées les plus récentes, pour les statistiques paper (§9.5)."""
    if not exclusion_active():
        return portfolio_db.lire_positions_recentes_fermees(limite)
    conn = database.get_connection()
    try:
        if not colonne_presente(conn):
            logger.warning("EXCLURE_BOUCLES_STATS=1 mais colonne boucle absente (scripts/marquer_boucles.py "
                           "non appliqué) : aucune exclusion")
            return portfolio_db.lire_positions_recentes_fermees(limite)
        rows = conn.execute("SELECT * FROM positions WHERE status != 'OPEN' AND COALESCE(boucle, 0) = 0 "
                            "ORDER BY exit_date DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def nombre_marquees() -> int | None:
    """Positions marquées « boucle », en lecture seule (empreinte des paramètres du registre, §9.2).
    None si la base ou la colonne est absente ; n'ouvre jamais la base en écriture."""
    chemin = database.DB_PATH
    if not os.path.exists(chemin):
        return None
    try:
        conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
        try:
            if not colonne_presente(conn):
                return None
            return conn.execute("SELECT COUNT(*) FROM positions WHERE boucle = 1").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning(f"nombre_marquees : {e}")
        return None
