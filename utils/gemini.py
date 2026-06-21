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
import threading
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
import config

logger = get_logger(__name__)

MODEL_NAME            = "gemini-2.5-flash"
MAX_RETRIES           = 3
INITIAL_BACKOFF_SEC   = 2.0      # 2s → 4s → 8s
MAX_REQUESTS_PER_MIN  = 10       # cap local pour ne pas dépasser le tier gratuit
REQUEST_TIMEOUT_SEC   = 30

# ── État partagé ────────────────────────────────────────────────────────────
_client = None
_client_lock = threading.Lock()
_request_times: deque[float] = deque(maxlen=MAX_REQUESTS_PER_MIN)
_rate_lock = threading.Lock()


def _get_client():
    """Initialise (paresseusement) le client Gemini. Thread-safe."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        key = config.GEMINI_API_KEY
        if not key:
            logger.warning("GEMINI_API_KEY non configurée — Gemini désactivé")
            return None
        try:
            from google import genai
            _client = genai.Client(api_key=key)
            logger.info(f"Client Gemini initialisé ({MODEL_NAME})")
        except Exception as e:
            logger.error(f"Init Gemini : {e}")
            _client = None
        return _client


def _respecter_rate_limit() -> None:
    """Attend si on s'approche de la limite (10 req/min)."""
    with _rate_lock:
        now = time.time()
        # Nettoie les requêtes > 60s
        while _request_times and now - _request_times[0] > 60:
            _request_times.popleft()
        if len(_request_times) >= MAX_REQUESTS_PER_MIN:
            attente = 60 - (now - _request_times[0]) + 0.5
            if attente > 0:
                logger.info(f"Rate limit local atteint — pause {attente:.1f}s")
                time.sleep(attente)
                # Re-clean après attente
                now = time.time()
                while _request_times and now - _request_times[0] > 60:
                    _request_times.popleft()
        _request_times.append(time.time())


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

    backoff = INITIAL_BACKOFF_SEC
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
            msg = str(e).lower()
            is_rate = ("429" in msg or "rate" in msg or "quota" in msg
                       or "resource_exhausted" in msg)
            if is_rate and tentative < MAX_RETRIES:
                logger.warning(
                    f"Gemini 429/rate limit (tentative {tentative}/{MAX_RETRIES})"
                    f" — backoff {backoff:.0f}s"
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            logger.error(f"Gemini échec (tentative {tentative}) : {e}")
            return ""
    return ""


def gemini_disponible() -> bool:
    """Vérifie rapidement que Gemini est utilisable."""
    return _get_client() is not None


def stats_usage() -> dict:
    """Stats du rate-limiting local (debug)."""
    with _rate_lock:
        now = time.time()
        recents = [t for t in _request_times if now - t <= 60]
        return {
            "requetes_dernieres_60s": len(recents),
            "plafond_local_min":       MAX_REQUESTS_PER_MIN,
            "modele":                  MODEL_NAME,
            "configure":               bool(config.GEMINI_API_KEY),
        }
