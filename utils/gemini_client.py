"""
utils/gemini_client.py — Client Gemini (initialisation paresseuse) et limite locale de requêtes
par minute, avec leur état partagé.
Sorti de utils/gemini.py (règle des 200 lignes) ; gemini.py le réexporte. L'état (_client,
_request_times) n'est lu et écrit que par les deux fonctions de ce module.
"""

import time
import threading
from collections import deque

import config
from utils.logger import get_logger

logger = get_logger("utils.gemini")  # même nom de journal qu'avant le découpage


MODEL_NAME            = "gemini-2.5-flash"
MAX_REQUESTS_PER_MIN  = 5        # tier gratuit gemini-2.5-flash = 5 req/min

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
