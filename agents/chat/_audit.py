"""
agents/chat/_audit.py — Audit des messages du chat stratégique (Phase 4).

Décorateur @auditer_message posé sur :
  - chat_engine.repondre            (/api/chat/message     → source pwa)
  - plan_builder.etape_creation_plan (/api/chat/create-plan → source pwa_plan)

Il ouvre une trace (utils/audit_trace), laisse la fonction s'exécuter
normalement, puis construit l'enregistrement message_audit et l'écrit en
arrière-plan.

Garanties : l'audit ne modifie jamais la réponse, ne la retarde pas
(écriture SQLite dans un thread) et ne la fait jamais échouer — toute
erreur d'audit est loggée puis ignorée. Une exception de la fonction
auditée est enregistrée, puis relancée telle quelle.
"""

import functools
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from utils.logger import get_logger
from utils.audit_trace import demarrer_trace, arreter_trace
from utils.message_audit_db import enregistrer_en_arriere_plan
from agents.chat._audit_record import construire_enregistrement

logger = get_logger(__name__)


def _origine_client() -> dict:
    """Qui a envoyé le message : route, page d'origine, identité Tailscale."""
    try:
        from flask import has_request_context, request
        if not has_request_context():
            return {"route": None, "hors_requete_http": True}
        h = request.headers
        return {
            "route":          request.path,
            "referer_path":   urlparse(h.get("Referer") or "").path or None,
            # Tailscale Serve ajoute ces en-têtes ; absents = accès local direct
            "via":            "tailscale" if (h.get("Tailscale-User-Login")
                                              or h.get("X-Forwarded-For")) else "local",
            "tailscale_user": h.get("Tailscale-User-Login"),
            "x_forwarded_for": h.get("X-Forwarded-For"),
            "user_agent":     (h.get("User-Agent") or "")[:160],
        }
    except Exception as e:
        return {"erreur": str(e)[:200]}


def auditer_message(type_message: str):
    """type_message : "chat" (repondre) ou "plan" (etape_creation_plan)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                trace, jeton = demarrer_trace()
            except Exception as e:
                logger.error(f"Audit (démarrage) : {e}")
                return fn(*args, **kwargs)
            horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
            debut = time.monotonic()
            resultat, exc = None, None
            try:
                resultat = fn(*args, **kwargs)
                return resultat
            except Exception as e:
                exc = e
                raise
            finally:
                arreter_trace(jeton)
                try:
                    enr = construire_enregistrement(
                        type_message, args, kwargs, trace, resultat, exc,
                        horodatage, int((time.monotonic() - debut) * 1000),
                        _origine_client())
                    enregistrer_en_arriere_plan(enr)
                except Exception as e:
                    logger.error(f"Audit message non enregistré : {e}")
        return wrapper
    return deco
