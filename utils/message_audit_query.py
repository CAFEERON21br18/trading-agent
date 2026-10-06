"""
utils/message_audit_query.py — Lecture de message_audit pour l'API (Phase 4, partie C).

LECTURE SEULE : connexion SQLite ouverte en mode=ro, aucune fonction d'écriture
ni de suppression ici. La seule suppression est la purge de rétention
(utils/message_audit_db.purger_audit), lancée par le cycle cleanup.

« Actions déclenchées » (définition Phase 4) : au moins une écriture persistante
hors caches, ou un decider() lancé. Les appels LLM sont comptés, mais ne font
pas à eux seuls une action (chaque message du chat en fait un).
"""

import json
import sqlite3
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import config
from utils.database import DB_PATH

SOURCES = ("pwa", "pwa_plan", "autre")
LLMS = ("gemini", "groq", "rule_based")
PAR_PAGE_DEFAUT, PAR_PAGE_MAX = 50, 200

# Liste légère : ni prompt_envoye ni contexte_injecte ; réponse tronquée côté SQL
_COLONNES_LISTE = ("id, timestamp, source, message_utilisateur, llm_utilise, chaine_de_fallback, "
                   "substr(reponse_brute, 1, 201) AS reponse_brute, actions_declenchees, "
                   "decisions_trading_generees, passe_par_decision_engine, passe_par_budget_manager, "
                   "latence_ms, erreur, origine_client")
_CHAMPS_JSON = ("contexte_injecte", "chaine_de_fallback", "actions_declenchees",
                "decisions_trading_generees", "origine_client")
_SQL_ACTIONS = ("(COALESCE(json_array_length(actions_declenchees, '$.decider_lances'), 0) > 0 "
                "OR EXISTS (SELECT 1 FROM json_each(actions_declenchees, '$.ecritures') "
                "WHERE json_extract(value, '$.categorie') = 'persistante'))")
_SQL_CONTOURNEMENT = ("(COALESCE(passe_par_decision_engine, 1) = 0 "
                      "OR COALESCE(passe_par_budget_manager, 1) = 0)")


def _connexion_lecture() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _json(valeur):
    try:
        return json.loads(valeur) if valeur else None
    except ValueError:
        return None


def _jour_utc(jour: str, lendemain: bool = False) -> str:
    """'2026-10-03' (jour local, config.TIMEZONE) → borne UTC ISO, comparable à timestamp."""
    d = datetime.strptime(jour, "%Y-%m-%d").date() + timedelta(days=1 if lendemain else 0)
    return (datetime.combine(d, time.min, ZoneInfo(config.TIMEZONE))
            .astimezone(timezone.utc).isoformat(timespec="seconds"))


def construire_filtres(f: dict) -> tuple[str, list]:
    """f : du / au (AAAA-MM-JJ, jours locaux inclus), source, llm,
    erreur / actions / contournement (True, False ou absent). ValueError si invalide."""
    where, params = [], []
    if f.get("du"):
        where.append("timestamp >= ?"); params.append(_jour_utc(f["du"]))
    if f.get("au"):
        where.append("timestamp < ?"); params.append(_jour_utc(f["au"], lendemain=True))
    if f.get("du") and f.get("au") and f["du"] > f["au"]:
        raise ValueError("« du » doit précéder « au »")
    for cle, valides, colonne in (("source", SOURCES, "source"), ("llm", LLMS, "llm_utilise")):
        if f.get(cle):
            if f[cle] not in valides:
                raise ValueError(f"{cle} invalide : {f[cle]!r} (attendu : {', '.join(valides)})")
            where.append(f"{colonne} = ?"); params.append(f[cle])
    for cle, sql in (("erreur", "erreur IS NOT NULL"), ("actions", _SQL_ACTIONS),
                     ("contournement", _SQL_CONTOURNEMENT)):
        if f.get(cle) is True:
            where.append(sql)
        elif f.get(cle) is False:
            where.append(f"NOT {sql}")
    return (" WHERE " + " AND ".join(where)) if where else "", params


def _resume(r: dict) -> dict:
    """Ligne légère pour la liste (timeline)."""
    act = _json(r["actions_declenchees"]) or {}
    ecritures = [e for e in act.get("ecritures", []) if e.get("categorie") == "persistante"]
    rep = r["reponse_brute"] or ""
    pde, pbm = r["passe_par_decision_engine"], r["passe_par_budget_manager"]
    return {
        "id": r["id"], "timestamp": r["timestamp"], "source": r["source"],
        "message_utilisateur": r["message_utilisateur"], "llm_utilise": r["llm_utilise"],
        "erreur": r["erreur"], "latence_ms": r["latence_ms"],
        "passe_par_decision_engine": pde, "passe_par_budget_manager": pbm,
        "contournement": 0 in (pde, pbm),
        "actions": bool(ecritures or act.get("decider_lances")),
        "decider_lances": act.get("decider_lances", []),
        "ecritures_persistantes": [f"{e.get('operation')} {e.get('cible')}" for e in ecritures],
        "appels_llm": (act.get("appels_llm") or {}).get("total", 0),
        "fallback": [{**{k: e.get(k) for k in ("fournisseur", "ok", "type_erreur")},
                      **({"statut": e["statut"]} if e.get("statut") else {})}  # Q4 : « réservé »
                     for e in (_json(r["chaine_de_fallback"]) or []) if e.get("fournisseur")],
        "decisions": [{"cible": d.get("cible"), **(d.get("resultat") or {})}
                      for d in (_json(r["decisions_trading_generees"]) or [])],
        "extrait_reponse": rep[:200] + ("…" if len(rep) > 200 else ""),
        "via": (_json(r["origine_client"]) or {}).get("via"),
    }


def lister_messages(filtres: dict, page: int = 1, par_page: int = PAR_PAGE_DEFAUT) -> dict:
    """Page de la liste légère, plus récents d'abord."""
    where, params = construire_filtres(filtres)
    page, par_page = max(1, page), max(1, min(PAR_PAGE_MAX, par_page))
    conn = _connexion_lecture()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM message_audit{where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT {_COLONNES_LISTE} FROM message_audit{where} "
                            "ORDER BY id DESC LIMIT ? OFFSET ?",
                            params + [par_page, (page - 1) * par_page]).fetchall()
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        total, rows = 0, []
    finally:
        conn.close()
    return {"total": total, "page": page, "par_page": par_page,
            "pages": (total + par_page - 1) // par_page, "filtres": filtres,
            "messages": [_resume(dict(r)) for r in rows]}


def lire_message(audit_id: int) -> dict | None:
    """Enregistrement complet (prompt, contexte…), champs JSON décodés."""
    conn = _connexion_lecture()
    try:
        row = conn.execute("SELECT * FROM message_audit WHERE id = ?", (audit_id,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()
    if row is None:
        return None
    r = dict(row)
    for c in _CHAMPS_JSON:
        r[c] = _json(r[c])
    return r
