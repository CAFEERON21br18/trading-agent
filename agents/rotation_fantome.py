"""
agents/rotation_fantome.py — Rotation v5 (agents/paper_trader/rotation.py) en OBSERVATION seulement (TODO §17).

À chaque cycle quotidien, après toute la routine (scripts/cycle_daily.py, BLOCS_DE_FIN) : si les slots
paper sont pleins et qu'une opportunité BUY ou SELL du passage a été refusée, rotation.suggerer_rotation
dit quelle position elle aurait fermée. RIEN n'est fermé : la proposition va dans la table
rotation_hypothetique de data/database.db. Les opportunités refusées viennent du registre du jour
(data/registre.db ouvert en mode=ro : jamais écrit), dernier passage « quotidien », origine « cycle ».
ROTATION_ACTIVE=0 par défaut ; à 1, le code refuse d'agir, journalise MESSAGE_REFUS et reste en observation.
"""

import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

LISBONNE = ZoneInfo("Europe/Lisbon")
MESSAGE_REFUS = "activation non autorisée : critère du registre requis"
DDL = """CREATE TABLE IF NOT EXISTS rotation_hypothetique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jour TEXT NOT NULL,                 -- AAAA-MM-JJ, jour de Lisbonne
    horodatage TEXT NOT NULL,           -- UTC
    cycle TEXT NOT NULL,
    passage_id TEXT,
    position_id INTEGER NOT NULL,       -- position paper qu'elle aurait fermée (jamais fermée)
    position_ticker TEXT NOT NULL,
    position_confiance INTEGER,
    position_score_rotation REAL,       -- rotation._score_position
    opportunite_ticker TEXT NOT NULL,
    opportunite_decision TEXT NOT NULL,
    opportunite_confiance INTEGER,
    opportunite_score REAL,             -- score composite du Decision Engine
    ecart_confiance INTEGER,            -- confiance de l'opportunité − confiance d'entrée de la position
    raison TEXT,
    UNIQUE (passage_id, opportunite_ticker))"""


def _jour(horodatage: str):
    t = datetime.fromisoformat(horodatage)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(LISBONNE).date()


def refusees_du_passage(jour, chemin_registre: str | None = None) -> tuple[str | None, list[dict]]:
    """(passage_id, opportunités BUY/SELL refusées) du dernier passage quotidien du jour (mode=ro)."""
    from utils.registre import CHEMIN
    conn = sqlite3.connect(f"file:{chemin_registre or CHEMIN}?mode=ro", uri=True)
    try:
        lignes = conn.execute("SELECT passage_id, horodatage, ticker, decision, confiance, score, contenu FROM registre "
                              "WHERE type = 'decision' AND cycle = 'quotidien' ORDER BY id DESC LIMIT 500").fetchall()
    finally:
        conn.close()
    if not lignes or _jour(lignes[0][1]) != jour:
        return None, []
    passage = lignes[0][0]
    out = []
    for p, _, ticker, decision, confiance, score, contenu in lignes:
        c = json.loads(contenu or "{}")
        if (p == passage and decision in ("BUY", "SELL") and c.get("origine") == "cycle"
                and (c.get("suite") or {}).get("resultat") == "refusee"):
            out.append({"ticker": ticker, "decision": decision, "confiance": confiance, "score": score})
    return passage, out[::-1]


def _enregistrer(conn, ligne: dict) -> int:
    cols = list(ligne)
    return conn.execute(f"INSERT OR IGNORE INTO rotation_hypothetique ({', '.join(cols)}) "
                        f"VALUES ({', '.join('?' * len(cols))})", [ligne[c] for c in cols]).rowcount


def observer_cycle(maintenant: datetime | None = None, chemin_registre: str | None = None) -> int:
    """Nombre de propositions enregistrées ; ne ferme jamais aucune position."""
    if config.ROTATION_ACTIVE:
        logger.error(f"Rotation v5 : {MESSAGE_REFUS} (ROTATION_ACTIVE=1 ignoré, observation seulement)")
    from agents.paper_trader import rotation
    if rotation.position_la_plus_faible() is None:  # slots non pleins : rien à proposer
        return 0
    maintenant = maintenant or datetime.now(timezone.utc)
    jour = maintenant.astimezone(LISBONNE).date()
    passage, refusees = refusees_du_passage(jour, chemin_registre)
    n = 0
    conn = get_connection()
    try:
        conn.execute(DDL)
        for o in refusees:
            s = rotation.suggerer_rotation(int(o["confiance"] or 0), float(o["score"] or 0))
            if not s:
                continue
            p = s["position_a_fermer"]
            n += _enregistrer(conn, {
                "jour": jour.isoformat(), "horodatage": maintenant.isoformat(timespec="seconds"),
                "cycle": "quotidien", "passage_id": passage, "position_id": p["id"],
                "position_ticker": p["ticker"], "position_confiance": p.get("confidence"),
                "position_score_rotation": round(s["score_actuel"], 3), "opportunite_ticker": o["ticker"],
                "opportunite_decision": o["decision"], "opportunite_confiance": o["confiance"],
                "opportunite_score": o["score"],
                "ecart_confiance": int(o["confiance"] or 0) - int(p.get("confidence") or 0),
                "raison": s["raison"][:200]})
        conn.commit()
    finally:
        conn.close()
    if n:
        logger.info(f"Rotation v5 (observation) : {n} proposition(s) enregistrée(s), aucune position fermée")
    return n
