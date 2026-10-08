"""
utils/message_audit_db.py — Table message_audit : journal d'audit du chat (Phase 4).

Migration additive : CREATE TABLE IF NOT EXISTS, puis ADD COLUMN des colonnes
ajoutées depuis (verification_chiffres), seulement si elles manquent ; aucune
autre table touchée. Indépendante de chat_history : le bouton « Effacer » du
chat (DELETE /api/chat/history) n'y touche jamais.

L'écriture se fait dans un thread séparé, sur sa propre connexion : elle
ne retarde jamais la réponse du chat. Si la base est verrouillée (cycle en
cours d'écriture), elle attend au plus TIMEOUT_VERROU_SEC puis abandonne :
l'échec est seulement loggé, la réponse est déjà partie.
"""

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

TIMEOUT_VERROU_SEC = 10  # attente max d'un verrou SQLite avant abandon (loggé)
TIMEOUT_PURGE_SEC = 30   # la purge attend la fin d'une écriture d'audit en cours

COLONNES = (
    "timestamp", "source", "message_utilisateur", "contexte_injecte",
    "llm_utilise", "chaine_de_fallback", "prompt_envoye", "reponse_brute",
    "actions_declenchees", "decisions_trading_generees",
    "passe_par_decision_engine", "passe_par_budget_manager",
    "latence_ms", "erreur", "origine_client", "verification_chiffres",
)
# Colonnes ajoutées après la création de la table (migration additive, dans l'ordre)
_COLONNES_AJOUTEES = (("verification_chiffres", "TEXT"),)

_DDL_TABLE = """
    CREATE TABLE IF NOT EXISTS message_audit (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp                   TEXT NOT NULL,  -- début de la requête (UTC ISO)
        source                      TEXT NOT NULL,  -- pwa | pwa_plan | autre
        message_utilisateur         TEXT,
        contexte_injecte            TEXT,           -- JSON
        llm_utilise                 TEXT,           -- gemini | groq | rule_based
        chaine_de_fallback          TEXT,           -- JSON : config + chaque tentative
        prompt_envoye               TEXT,
        reponse_brute               TEXT,
        actions_declenchees         TEXT,           -- JSON : écritures, decider, appels LLM
        decisions_trading_generees  TEXT,           -- JSON
        passe_par_decision_engine   INTEGER,        -- 1/0 ; NULL = aucune écriture persistante
        passe_par_budget_manager    INTEGER,        -- 1/0 ; NULL = aucune écriture persistante
        latence_ms                  INTEGER,
        erreur                      TEXT,
        origine_client              TEXT,           -- JSON : route, referer, Tailscale, UA
        verification_chiffres       TEXT            -- JSON : chiffres de la réponse LLM absents du prompt
    )
"""
_DDL_INDEX = "CREATE INDEX IF NOT EXISTS idx_message_audit_timestamp ON message_audit (timestamp)"


def initialiser_audit_db(conn=None) -> None:
    """Crée la table et son index si besoin, ajoute les colonnes manquantes (idempotent)."""
    propre = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(_DDL_TABLE)
        conn.execute(_DDL_INDEX)
        _ajouter_colonnes_manquantes(conn)
        conn.commit()
    finally:
        if propre:
            conn.close()


def _ajouter_colonnes_manquantes(conn) -> None:
    """ALTER TABLE … ADD COLUMN seulement si PRAGMA table_info montre la colonne absente."""
    presentes = {r[1] for r in conn.execute("PRAGMA table_info(message_audit)")}
    for nom, type_sql in _COLONNES_AJOUTEES:
        if nom in presentes:
            continue
        try:
            conn.execute(f"ALTER TABLE message_audit ADD COLUMN {nom} {type_sql}")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():  # sinon : ajoutée entre-temps par un autre processus
                raise


def inserer_audit(enregistrement: dict) -> int | None:
    """Insère un enregistrement (champs déjà masqués). Retourne son id.
    Connexion dédiée, jamais partagée avec la requête du chat."""
    conn = get_connection()
    try:
        conn.execute(f"PRAGMA busy_timeout = {TIMEOUT_VERROU_SEC * 1000}")
        initialiser_audit_db(conn)
        place = ", ".join("?" for _ in COLONNES)
        cur = conn.execute(
            f"INSERT INTO message_audit ({', '.join(COLONNES)}) VALUES ({place})",
            [enregistrement.get(c) for c in COLONNES])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def purger_audit(jours: int) -> int:
    """Rétention (Phase 4, partie C) : supprime les lignes de plus de `jours` jours.
    Retourne le nombre de lignes supprimées ; jours ≤ 0 → purge désactivée.

    Concurrence avec le chat, sans lock manager : une seule transaction DELETE,
    et SQLite n'admet qu'un écrivain à la fois — une écriture d'audit en cours
    fait attendre la purge (busy_timeout), et inversement. Une ligne en cours
    d'écriture porte l'heure du moment : jamais concernée par la coupure.
    Seule suppression de message_audit dans tout le code (aucune route HTTP)."""
    if jours <= 0:
        return 0
    seuil = (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute(f"PRAGMA busy_timeout = {TIMEOUT_PURGE_SEC * 1000}")
        initialiser_audit_db(conn)
        cur = conn.execute("DELETE FROM message_audit WHERE timestamp < ?", (seuil,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def enregistrer_en_arriere_plan(enregistrement: dict) -> threading.Thread:
    """Écrit l'enregistrement dans un thread : jamais bloquant, jamais d'exception."""
    def _ecrire():
        try:
            rid = inserer_audit(enregistrement)
            logger.info(f"Audit message #{rid} ({enregistrement.get('source')}, "
                        f"{enregistrement.get('llm_utilise')}, {enregistrement.get('latence_ms')} ms)")
        except Exception as e:
            logger.error(f"Audit message non écrit dans message_audit : {e}")

    t = threading.Thread(target=_ecrire, name="message_audit", daemon=True)
    t.start()
    return t
