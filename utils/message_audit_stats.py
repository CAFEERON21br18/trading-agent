"""
utils/message_audit_stats.py — Synthèse de message_audit (Phase 4, partie C).

Sert à mesurer l'état du chat avant le chantier des quotas LLM : volume de
messages, répartition gemini / groq / rule_based, et par jour sur 7 jours
(jours locaux, config.TIMEZONE). LECTURE SEULE.

Le mode plan (source pwa_plan) est toujours rule_based : pour la santé des LLM
du chat, filtrer sur source=pwa.
"""

import sqlite3
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import config
from utils.message_audit_query import LLMS, SOURCES, _connexion_lecture


def statistiques(source: str | None = None, jours: int = 7) -> dict:
    if source and source not in SOURCES:
        raise ValueError(f"source invalide : {source!r} (attendu : {', '.join(SOURCES)})")
    tz = ZoneInfo(config.TIMEZONE)
    aujourd_hui = datetime.now(tz).date()
    premier = aujourd_hui - timedelta(days=jours - 1)
    debut_utc = (datetime.combine(premier, time.min, tz)
                 .astimezone(timezone.utc).isoformat(timespec="seconds"))
    filtre, params = (" AND source = ?", [source]) if source else ("", [])

    conn = _connexion_lecture()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM message_audit WHERE 1=1{filtre}", params).fetchone()[0]
        par_llm = Counter(dict(conn.execute(
            f"SELECT llm_utilise, COUNT(*) FROM message_audit WHERE 1=1{filtre} GROUP BY llm_utilise",
            params).fetchall()))
        par_source = dict(conn.execute(
            f"SELECT source, COUNT(*) FROM message_audit WHERE 1=1{filtre} GROUP BY source",
            params).fetchall())
        recents = conn.execute(f"SELECT timestamp, llm_utilise FROM message_audit "
                               f"WHERE timestamp >= ?{filtre}", [debut_utc] + params).fetchall()
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        total, par_llm, par_source, recents = 0, Counter(), {}, []
    finally:
        conn.close()

    jours_liste = {premier + timedelta(days=i): Counter() for i in range(jours)}
    for ts, llm in recents:
        jour = datetime.fromisoformat(ts).astimezone(tz).date()
        if jour in jours_liste:
            jours_liste[jour][llm or "inconnu"] += 1
    return {
        "source": source or "toutes",
        "total": total,
        "par_llm": {l: par_llm.get(l, 0) for l in LLMS},
        "par_source": par_source,
        "total_7_jours": len(recents),
        "par_jour": [{"date": j.isoformat(), "total": sum(c.values()),
                      **{l: c.get(l, 0) for l in LLMS}} for j, c in jours_liste.items()],
        "fuseau": config.TIMEZONE,
        "conservation_jours": config.AUDIT_RETENTION_DAYS,
    }
