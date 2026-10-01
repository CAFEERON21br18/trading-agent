"""
utils/audit_trace.py — Trace d'audit d'un message du chat stratégique (Phase 4).

Une trace est ouverte pour la durée d'une requête du chat (ContextVar :
propre au thread de la requête Flask). Les points instrumentés y déposent
ce qu'ils déclenchent : appels LLM, écritures SQLite et fichiers, passages
dans le Decision Engine et le Budget Manager.

Hors requête auditée (cycles, scripts), toutes les fonctions sont des no-op :
aucun changement de comportement pour le reste du système. Aucune fonction
de ce module ne lève d'exception vers l'appelant.
"""

import functools
import re
import time
from contextvars import ContextVar

from utils.logger import get_logger

logger = get_logger(__name__)

# Écritures qui ne comptent pas comme « actions » (définition validée Phase 4)
TABLES_EXCLUES = {"chat_history", "message_audit"}
# Caches de données de marché : tracés, mais exclus du calcul passe_par_*
TABLES_CACHE = {"prices", "indicators", "sentiment"}

_RE_ECRITURE = re.compile(
    r"^\s*(INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)"
    r"\s+[\"`\[]?(\w+)", re.IGNORECASE)

_TRACE: ContextVar["TraceAudit | None"] = ContextVar("trace_audit", default=None)


class TraceAudit:
    """Ce qu'une requête du chat a déclenché."""

    def __init__(self):
        self.zones: list[str] = []                # pile : decision_engine, budget_manager
        self.contexte = None                      # contexte injecté au LLM
        self.appel_principal: dict | None = None  # 1er ask_llm hors zone = appel du chat
        self.appels_llm: list[dict] = []
        self.ecritures: dict[tuple, int] = {}     # (type, cible, op, via_de, via_bm) → nb
        self.invocations: list[dict] = []         # decider / traiter_demandes lancés

    def ajouter_ecriture(self, type_: str, cible: str, operation: str, nb: int = 1) -> None:
        cle = (type_, cible, operation,
               "decision_engine" in self.zones, "budget_manager" in self.zones)
        self.ecritures[cle] = self.ecritures.get(cle, 0) + nb


def demarrer_trace() -> tuple[TraceAudit, object]:
    """Ouvre une trace pour la requête courante. Retourne (trace, jeton)."""
    trace = TraceAudit()
    return trace, _TRACE.set(trace)


def arreter_trace(jeton) -> None:
    try:
        _TRACE.reset(jeton)
    except Exception as e:
        logger.warning(f"Audit : fermeture de trace impossible : {e}")


def noter_contexte(contexte) -> None:
    """Contexte injecté au LLM (ou état de session du plan)."""
    trace = _TRACE.get()
    if trace is not None:
        trace.contexte = contexte


def noter_ecriture(type_: str, cible: str, operation: str = "write") -> None:
    """Écriture persistante hors SQLite (ex. memory/metacognition_log.md)."""
    trace = _TRACE.get()
    if trace is None:
        return
    try:
        trace.ajouter_ecriture(type_, cible, operation)
    except Exception as e:
        logger.warning(f"Audit : écriture non notée ({cible}) : {e}")


def noter_appel_llm(fonction: str, prompt, system, resultat, duree_ms: int | None = None) -> None:
    """Appel LLM. Le 1er ask_llm hors Decision Engine / BM est l'appel du chat."""
    trace = _TRACE.get()
    if trace is None:
        return
    try:
        if isinstance(resultat, dict):
            source = resultat.get("source")
            ok = bool(resultat.get("text")) and source is not None
        else:
            ok = bool(resultat)
            source = "gemini" if ok else None
        appelant = trace.zones[-1] if trace.zones else "chat"
        trace.appels_llm.append({"appelant": appelant, "fonction": fonction,
                                 "source": source, "ok": ok, "duree_ms": duree_ms})
        if appelant == "chat" and fonction == "ask_llm" and trace.appel_principal is None:
            trace.appel_principal = {"prompt": prompt, "system": system, "resultat": resultat}
    except Exception as e:
        logger.warning(f"Audit : appel LLM non noté : {e}")


def tracer_sql(conn) -> None:
    """Branche le traceur d'écritures SQL sur une connexion si une trace est ouverte."""
    trace = _TRACE.get()
    if trace is None:
        return

    def _sur_requete(sql: str) -> None:
        try:
            m = _RE_ECRITURE.match(sql or "")
            if m and m.group(2).lower() not in TABLES_EXCLUES:
                trace.ajouter_ecriture("sqlite", m.group(2).lower(), m.group(1).split()[0].upper())
        except Exception:
            pass  # le traceur ne doit jamais perturber une requête SQL

    try:
        conn.set_trace_callback(_sur_requete)
    except Exception as e:
        logger.warning(f"Audit : traceur SQL non branché : {e}")


def _resumer(resultat) -> dict | None:
    """Résumé compact d'une décision (DE) ou d'une allocation (BM)."""
    if not isinstance(resultat, dict):
        return None
    cles = ("decision", "confidence", "score_composite", "style", "taille_factor",
            "quality_grade", "mode", "cash_dispo", "total_alloue")
    resume = {k: resultat[k] for k in cles if k in resultat}
    if isinstance(resultat.get("allocations"), list):
        resume["nb_allocations"] = len(resultat["allocations"])
    return resume


def zone_audit(nom: str):
    """Décorateur : marque la zone (decision_engine / budget_manager) et note l'invocation.
    Hors trace : appel direct de la fonction, rien d'autre."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            trace = _TRACE.get()
            if trace is None:
                return fn(*args, **kwargs)
            cible = args[0] if args and isinstance(args[0], str) else None
            invocation = {"zone": nom, "fonction": fn.__name__, "cible": cible}
            trace.invocations.append(invocation)
            trace.zones.append(nom)
            debut = time.monotonic()
            try:
                resultat = fn(*args, **kwargs)
                invocation["resultat"] = _resumer(resultat)
                return resultat
            except Exception as e:
                invocation["erreur"] = f"{type(e).__name__}: {e}"[:300]
                raise
            finally:
                invocation["duree_ms"] = int((time.monotonic() - debut) * 1000)
                trace.zones.pop()
        return wrapper
    return deco


def compter_appel_llm(fn):
    """Décorateur pour les helpers LLM directs (ask_gemini) : compte l'appel."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if _TRACE.get() is None:
            return fn(*args, **kwargs)
        debut = time.monotonic()
        resultat = fn(*args, **kwargs)
        noter_appel_llm(fn.__name__, None, None, resultat,
                        int((time.monotonic() - debut) * 1000))
        return resultat
    return wrapper
