"""
utils/registre_cycles.py — Branchement du registre dans les cycles (Phase 4, R2).

Construit le résumé compact d'une décision : contribution de chaque sous-agent,
pipeline, risque, fraîcheur de la dernière barre, suite donnée par le Budget
Manager et le Paper Trader. Enregistre aussi les événements de position
(clôture, stop déplacé). Les réévaluations « GARDER » ne sont pas enregistrées.
Rien ici ne lève d'exception vers un cycle : un échec est compté dans le passage.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils import registre
from utils.valeurs import nombre_ou_none

logger = get_logger(__name__)


def ouvrir(cycle: str, **details):
    """Passage du cycle, ou None si le registre est indisponible (le cycle continue).
    details (R3) : recopiés dans la ligne de clôture (ex. déclencheur d'une intervention manuelle)."""
    try:
        if cycle == "manuel":  # R3 : le dashboard tourne longtemps, relire le commit courant
            registre.version_code.cache_clear()
        p = registre.ouvrir_passage(cycle)
        p.t0, p.details = time.monotonic(), {k: v for k, v in details.items() if v is not None}
        return p
    except Exception as e:
        logger.warning(f"Registre : passage {cycle} non ouvert : {e}")
        return None


def clore(passage, toujours: bool = True, details: dict | None = None) -> None:
    """Ligne de fin de passage. toujours=False : seulement si quelque chose a été écrit."""
    if passage is None or (not toujours and passage.ecrites + passage.erreurs == 0):
        return
    duree = round(time.monotonic() - getattr(passage, "t0", time.monotonic()), 1)
    registre.clore_passage(passage, passage.ecrites + passage.erreurs,
                           {"duree_s": duree, **getattr(passage, "details", {}), **(details or {})})


def _derniere_barre(ticker: str) -> dict | None:
    """Date et heure d'écriture de la dernière barre journalière (fraîcheur des données)."""
    try:
        from utils.database import get_connection
        conn = get_connection()
        try:
            r = conn.execute("SELECT timestamp, created_at FROM prices WHERE ticker = ? AND timeframe = '1d' "
                             "ORDER BY timestamp DESC LIMIT 1", (ticker,)).fetchone()
        finally:
            conn.close()
        return {"date": r[0][:10], "ecrite_le": r[1]} if r else None
    except Exception:
        return None


def _suite(ticker: str, decision: dict, execution: dict | None) -> dict:
    """Ce que le Budget Manager et le Paper Trader ont fait de la décision, dans ce passage."""
    if decision.get("decision") not in ("BUY", "SELL"):
        return {"resultat": "non_soumise"}
    if execution is None:
        return {"resultat": "erreur_execution"}
    alloue = {a["demande"]["actif"]: a.get("budget_alloue")
              for a in (execution.get("bm_resume") or {}).get("allocations", [])}
    for o in execution.get("ouvertes", []):
        if o.get("ticker") == ticker:
            return {"resultat": "ouverte", "position_id": o.get("pos_id"), "bm_alloue": o.get("budget")}
    for r in execution.get("refusees", []):
        if r.get("ticker") == ticker:
            return {"resultat": "refusee", "bm_alloue": alloue.get(ticker),
                    "raisons": [str(x)[:120] for x in (r.get("raisons") or [])[:3]]}
    return {"resultat": "non_traitee", "bm_alloue": alloue.get(ticker)}


def resume_decision(ticker: str, d: dict, analyses: dict, source: str, origine: str, suite: dict) -> tuple:
    """(champs, contenu) compacts d'une décision du Decision Engine."""
    pipe = d.get("pipeline_raisonnement") or {}
    risque, sig = analyses.get("risque") or {}, (analyses.get("risque") or {}).get("signal") or {}
    champs = {"decision": d.get("decision"), "style": d.get("style"), "score": d.get("score_composite"),
              "confiance": d.get("confidence"), "prix": (analyses.get("technique") or {}).get("prix"),
              "position_id": suite.get("position_id")}
    contenu = {
        "source": source, "origine": origine,
        "contributions": {nom: {"direction": (analyses.get(nom) or {}).get("direction"),
                                "confiance": (analyses.get(nom) or {}).get("confiance"),
                                "contribution": round(v, 3)} for nom, v in (d.get("scores_detail") or {}).items()},
        "overrides": [str(o)[:120] for o in (d.get("overrides") or [])],
        "convergences": len(d.get("convergences") or []), "contradictions": len(d.get("contradictions") or []),
        "qualite": d.get("quality_grade"), "taille_factor": d.get("taille_factor"),
        "pipeline": {"statut": ("cache" if pipe.get("cache") else "prudent" if pipe.get("fallback")
                                else "execute" if pipe.get("executed") else "saute"),
                     "raison": (str(pipe["raison"])[:120] if pipe.get("raison") else None),
                     "fournisseur": pipe.get("source"), "ajustement": pipe.get("taille_factor_ajustement"),
                     "verdicts": {k: (pipe.get(k) or {}).get("verdict") for k in ("pre_mortem", "metacognition", "base_rates")}},
        "risque": {"valide": risque.get("valide"), "rejets": [str(x)[:120] for x in (risque.get("rejets") or [])[:3]],
                   "stop": sig.get("stop_loss"), "objectif_1": sig.get("target_1"), "rr": sig.get("rr_1"), "atr": sig.get("atr")},
        "contexte": {"fg": (analyses.get("context") or {}).get("fg_valeur"),
                     "winrate_actif": ((analyses.get("memory") or {}).get("perf") or {}).get("winrate_pct")},
        "barre": _derniere_barre(ticker),
        "suite": suite,
    }
    return champs, contenu


def _sans_donnees(suite: dict, analyses: dict) -> dict:
    """R2c : décision prise sans prix (actif absent de la table prices, ex. ticker de la
    queue hors watchlist) → statut explicite, exclu des analyses R4 (REGISTRE_CRITERES
    v1.1). Seul l'enregistrement change : decider() et le cycle restent tels quels."""
    if nombre_ou_none((analyses.get("technique") or {}).get("prix")) is not None:
        return suite
    return {**suite, "resultat": "sans_donnees", "resultat_cycle": suite.get("resultat")}


def enregistrer_decisions(passage, decisions: list, execution: dict | None, source: str, origine: str = "cycle") -> None:
    """Une ligne par décision du passage ({ticker, decision, analyses}), avec sa suite."""
    if passage is None:
        return
    for x in decisions:
        try:
            suite = x.get("suite") or _suite(x["ticker"], x["decision"], execution)
            suite = _sans_donnees(suite, x["analyses"])
            champs, contenu = resume_decision(x["ticker"], x["decision"], x["analyses"], source, origine, suite)
            registre.enregistrer(passage, "decision", x["ticker"], champs, contenu)
        except Exception as e:
            passage.erreurs += 1
            logger.warning(f"Registre : résumé de la décision {x.get('ticker')} impossible : {e}")


def noter_evenement(passage, position: dict, evenement: str, prix=None, details: dict | None = None) -> None:
    """Événement de position : stop déplacé, clôture demandée non exécutée…"""
    if passage is not None:
        registre.enregistrer(passage, "reevaluation", position.get("ticker"),
                             {"decision": evenement, "prix": prix, "position_id": position.get("id")},
                             {"evenement": evenement.lower(), **(details or {})})


def noter_cloture(passage, position: dict, origine: str, raison: str | None = None) -> None:
    """Position fermée pendant le passage : statut, prix, raison et P&L relus en base."""
    if passage is None:
        return
    try:
        from utils.database import get_connection
        conn = get_connection()
        try:
            r = conn.execute("SELECT status, exit_price, exit_reason, pnl_euros, pnl_percent FROM positions "
                             "WHERE id = ?", (position["id"],)).fetchone()
        finally:
            conn.close()
        noter_evenement(passage, position, r[0] if r else "CLOSED_?", r[1] if r else None,
                        {"evenement": "cloture", "origine": origine, "raison": str(raison or (r[2] if r else "") or "")[:160],
                         "pnl_euros": r[3] if r else None, "pnl_pct": r[4] if r else None})
    except Exception as e:
        passage.erreurs += 1
        logger.warning(f"Registre : clôture de la position #{position.get('id')} non enregistrée : {e}")
