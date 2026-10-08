"""
utils/jev_db.py — Table jev_observations (observation Jev, REGISTRE_CRITERES §7).

Une ligne par actif et par appel du cycle quotidien, y compris les échecs
(statut "erreur") et les actifs écartés faute de budget (statut "ecarte").
Seules les lignes statut = "ok" sont des observations.
"""

import json
import sqlite3

from utils import database
from utils.database import get_connection

_DDL = (
    """CREATE TABLE IF NOT EXISTS jev_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        horodatage TEXT NOT NULL,              -- UTC ISO, début de l'appel
        jour TEXT NOT NULL,                    -- AAAA-MM-JJ, jour de Lisbonne
        ticker TEXT NOT NULL,
        cycle TEXT NOT NULL,                   -- quotidien
        statut TEXT NOT NULL,                  -- ok | erreur | ecarte
        erreur TEXT,
        questions_version TEXT NOT NULL,
        modele TEXT,                           -- version renvoyée (ex. jev-1.13.0)
        state TEXT,                            -- texte exact envoyé
        position_ouverte INTEGER,              -- 1 si position paper ouverte
        prix REAL,                             -- p0 : clôture utilisée par la décision
        decision_moteur TEXT,                  -- BUY | SELL | HOLD | NO_TRADE (non envoyée)
        style_moteur TEXT,
        score_moteur REAL,
        confiance_moteur INTEGER,
        action_jev TEXT,
        p_acheter REAL,
        p_conserver REAL,
        p_ne_rien_faire REAL,
        confiance REAL,                        -- confiance de la question action
        conviction_niveau INTEGER,
        conviction_score REAL,
        montant_risque REAL,                   -- montant_investi du Risk Manager
        plafond_bm REAL,                       -- max par trade du Budget Manager
        mode_bm TEXT,
        taille_hypothetique REAL,              -- jamais exécutée
        regime_jev TEXT,
        regime_moteur TEXT,
        reponses TEXT,                         -- JSON complet des réponses
        latence_ms INTEGER,
        jetons_entree INTEGER,
        jetons_sortie INTEGER)""",
    "CREATE INDEX IF NOT EXISTS idx_jev_obs_jour ON jev_observations (jour, ticker)",
)

COLONNES = ("horodatage", "jour", "ticker", "cycle", "statut", "erreur", "questions_version",
            "modele", "state", "position_ouverte", "prix", "decision_moteur", "style_moteur",
            "score_moteur", "confiance_moteur", "action_jev", "p_acheter", "p_conserver",
            "p_ne_rien_faire", "confiance", "conviction_niveau", "conviction_score",
            "montant_risque", "plafond_bm", "mode_bm", "taille_hypothetique", "regime_jev",
            "regime_moteur", "reponses", "latence_ms", "jetons_entree", "jetons_sortie")


def _connexion():
    conn = get_connection()
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def inserer(ligne: dict) -> None:
    """Insère une ligne ; les colonnes absentes restent NULL, reponses sérialisé en JSON."""
    valeurs = dict(ligne)
    if isinstance(valeurs.get("reponses"), (dict, list)):
        valeurs["reponses"] = json.dumps(valeurs["reponses"], ensure_ascii=False, default=str)
    conn = _connexion()
    try:
        conn.execute(f"INSERT INTO jev_observations ({', '.join(COLONNES)}) "
                     f"VALUES ({', '.join('?' for _ in COLONNES)})",
                     tuple(valeurs.get(c) for c in COLONNES))
        conn.commit()
    finally:
        conn.close()


def connexion_lecture() -> sqlite3.Connection:
    """Connexion en lecture seule (mode=ro) : n'écrit ni ne crée rien."""
    conn = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def lire(conn: sqlite3.Connection, cycle: str = "quotidien") -> list[dict]:
    """Toutes les lignes du cycle, triées par horodatage ; [] si la table n'existe pas."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                        "AND name = 'jev_observations'").fetchone():
        return []
    rows = conn.execute("SELECT * FROM jev_observations WHERE cycle = ? "
                        "ORDER BY horodatage, id", (cycle,)).fetchall()
    return [dict(r) for r in rows]
