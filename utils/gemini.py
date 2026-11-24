"""
utils/gemini.py — Point d'entrée unique vers Google Gemini (v5.3.3).

Tous les modules qui ont besoin d'un LLM (chat stratégique, analyse
fundamentale, raisonnement bayésien/pré-mortem/etc., rapports) passent
par ask_gemini(). Le helper :
  - Lit la clé via config.GEMINI_API_KEY
  - Utilise gemini-2.5-flash (tier gratuit)
  - Gère le rate limiting du tier gratuit (~10 req/min, ~500/jour)
    via retry exponentiel sur les erreurs 429
  - Ne crash JAMAIS l'agent : retourne "" en fallback et logge l'erreur
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.audit_trace import compter_appel_llm
from utils.gemini_erreurs import classer_erreur, message_brut, message_erreur, pause_minute
import config
from utils.gemini_client import (  # noqa: F401 — réexport
    MODEL_NAME, MAX_REQUESTS_PER_MIN, _get_client, _respecter_rate_limit,
)

logger = get_logger(__name__)

MAX_RETRIES           = 3
INITIAL_BACKOFF_SEC   = 2.0      # 503 : 2s → 4s (429 par minute : retryDelay de Google, Q5)
REQUEST_TIMEOUT_SEC   = 30


@compter_appel_llm  # audit du chat (Phase 4) : no-op hors requête auditée
def ask_gemini(prompt: str, system: str | None = None,
                temperature: float = 0.7,
                max_output_tokens: int | None = None) -> str:
    """
    Pose une question à Gemini et retourne sa réponse texte.
    Fallback gracieux : retourne "" si Gemini est indisponible.

    Args:
        prompt: La question / l'instruction principale.
        system: Instruction système (rôle, ton, format) — optionnel.
        temperature: 0.0 (déterministe) à 2.0 (créatif). Défaut 0.7.
        max_output_tokens: Limite optionnelle de tokens en sortie.

    Returns:
        Le texte généré, ou "" si erreur (jamais d'exception).
    """
    if not prompt or not prompt.strip():
        return ""
    client = _get_client()
    if client is None:
        return ""

    # Construction de la config
    from google.genai import types
    cfg_kwargs = {"temperature": temperature}
    if system:
        cfg_kwargs["system_instruction"] = system
    if max_output_tokens:
        cfg_kwargs["max_output_tokens"] = max_output_tokens
    cfg = types.GenerateContentConfig(**cfg_kwargs)

    for tentative in range(1, MAX_RETRIES + 1):
        try:
            _respecter_rate_limit()
            response = client.models.generate_content(
                model=MODEL_NAME, contents=prompt, config=cfg,
            )
            text = (response.text or "").strip()
            if text:
                return text
            logger.warning("Gemini a renvoyé une réponse vide")
            return ""
        except Exception as e:
            typ, _ = classer_erreur(e)  # Q5 : 429 classé d'après le quotaId de Google
            pause = (pause_minute(e, tentative, config.GEMINI_RETRY_MAX_SEC)
                     if typ == "rate_limit_minute" else None)
            if pause:  # retryDelay de Google ≤ seuil : une seule nouvelle tentative
                logger.warning(
                    f"Gemini rate_limit_minute (tentative {tentative}/{MAX_RETRIES})"
                    f" — nouvel essai dans {pause}s : {message_brut(e)}"
                )
                time.sleep(pause)
                continue
            logger.error(f"Gemini échec {typ} (tentative {tentative}) : {message_brut(e)}")
            return ""
    return ""


def ask_gemini_status(prompt: str, system: str | None = None,
                       temperature: float = 0.7,
                       max_output_tokens: int | None = None) -> dict:
    """
    Variante de ask_gemini qui retourne un dict structuré avec l'origine de l'échec.
    Utilisé par le chat pour afficher un message d'erreur clair à l'utilisateur.

    Returns:
        {"ok": bool, "text": str, "error_type": str | None,
         "error_message": str | None, "retry_after_sec": int | None}
        + "message_brut" (Q5 : erreur d'origine masquée) en cas d'exception

    error_type ∈ {"clé_manquante", "clé_invalide", "quota_quotidien",
                   "rate_limit_minute", "429_inconnu", "service_unavailable",
                   "réponse_vide", "réseau", "inconnu"}
    """
    if not prompt or not prompt.strip():
        return {"ok": False, "text": "", "error_type": "réponse_vide",
                "error_message": "Prompt vide", "retry_after_sec": None}

    client = _get_client()
    if client is None:
        return {"ok": False, "text": "", "error_type": "clé_manquante",
                "error_message": "Clé Gemini non configurée dans .env",
                "retry_after_sec": None}

    from google.genai import types
    cfg_kwargs = {"temperature": temperature}
    if system:
        cfg_kwargs["system_instruction"] = system
    if max_output_tokens:
        cfg_kwargs["max_output_tokens"] = max_output_tokens
    cfg = types.GenerateContentConfig(**cfg_kwargs)

    backoff = INITIAL_BACKOFF_SEC
    last_err = None
    for tentative in range(1, MAX_RETRIES + 1):
        try:
            _respecter_rate_limit()
            response = client.models.generate_content(
                model=MODEL_NAME, contents=prompt, config=cfg,
            )
            text = (response.text or "").strip()
            if text:
                return {"ok": True, "text": text, "error_type": None,
                        "error_message": None, "retry_after_sec": None}
            return {"ok": False, "text": "", "error_type": "réponse_vide",
                    "error_message": "Gemini a renvoyé une réponse vide",
                    "retry_after_sec": None}
        except Exception as e:
            last_err = e
            # Q5 : 429 classé d'après le quotaId de Google (par jour : échec immédiat ;
            # par minute : retryDelay de Google si ≤ GEMINI_RETRY_MAX_SEC, une seule
            # fois, sinon repli Groq ; sans identifiant : 429_inconnu)
            typ, limite = classer_erreur(e)
            brut = message_brut(e)
            pause = {"service_unavailable": backoff, "inconnu": 0}.get(typ)  # None : pas de nouvel essai
            if typ == "rate_limit_minute":
                pause = pause_minute(e, tentative, config.GEMINI_RETRY_MAX_SEC)
            essai = pause is not None and tentative < MAX_RETRIES
            suite = (f" — nouvel essai dans {pause:.0f}s" if essai and pause
                     else " — sans nouvel essai" if typ == "rate_limit_minute" else "")
            (logger.error if typ == "inconnu" else logger.warning)(
                f"Gemini {typ} (tentative {tentative}/{MAX_RETRIES}){suite} : {brut}")
            if essai:
                if pause:
                    time.sleep(pause); backoff *= 2
                continue
            retry = {"service_unavailable": 60, "clé_invalide": None,
                     "inconnu": None}.get(typ, _extraire_retry_delay(str(e)))
            return {"ok": False, "text": "", "error_type": typ,
                    "error_message": message_erreur(typ, limite, brut),
                    "message_brut": brut, "retry_after_sec": retry}

    return {"ok": False, "text": "", "error_type": "inconnu",
            "error_message": message_brut(last_err)[:200] if last_err else "?",
            "retry_after_sec": None}


def _extraire_retry_delay(msg: str) -> int | None:
    """Extrait le délai de l'erreur Google. Q5 : retryDelay (en secondes) d'abord,
    car « retry in 17h27m2s » était lu comme 17 secondes."""
    import re
    m = re.search(r"retryDelay':\s*'(\d+)s", msg)
    if m:
        return int(m.group(1))
    m = re.search(r"retry in (\d+)", msg)
    if m:
        return int(m.group(1))
    return None


def gemini_disponible() -> bool:
    """Vérifie rapidement que Gemini est utilisable."""
    return _get_client() is not None
