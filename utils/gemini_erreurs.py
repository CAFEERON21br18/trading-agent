"""
utils/gemini_erreurs.py — Classement des erreurs Gemini (Phase 4 / Q5).

Les 429 sont classés d'après l'identifiant de quota renvoyé par Google
(quotaId « …PerDay… » ou « …PerMinute… »), et non plus d'après « freetier »,
qui figure dans les deux. Identifiant absent : « 429_inconnu », sans deviner.
La limite citée vient de la réponse de Google (quotaValue), jamais codée en dur.
Le message brut est conservé, secrets masqués, pour les logs et l'audit.
"""

import re

from utils.secret_mask import masquer_secrets

# Assez long pour garder quotaId, quotaValue et retryDelay (≈ 1 300 car. chez Google)
TAILLE_MAX_BRUT = 1500

# Une violation de quota : quotaId puis, dans le même bloc, quotaValue
_VIOLATION = re.compile(r"quotaId['\"]?\s*:\s*['\"]?([\w-]+)['\"]?"
                        r"(?:(?!quotaId).)*?quotaValue['\"]?\s*:\s*['\"]?(\d+)", re.S)
_QUOTA_ID = re.compile(r"quotaId['\"]?\s*:\s*['\"]?([\w-]+)")
_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s")


def message_brut(e) -> str:
    """Erreur d'origine, secrets masqués, tronquée."""
    return masquer_secrets(str(e))[:TAILLE_MAX_BRUT]


def _est_429(e) -> bool:
    texte = str(e)
    return getattr(e, "code", None) == 429 or texte.startswith("429") or "RESOURCE_EXHAUSTED" in texte


def _classer_429(texte: str) -> tuple[str, int | None]:
    """Par jour l'emporte sur par minute si Google signale les deux."""
    limites = {qid: int(v) for qid, v in _VIOLATION.findall(texte)}
    ids = set(_QUOTA_ID.findall(texte))
    for motif, typ in (("PerDay", "quota_quotidien"), ("PerMinute", "rate_limit_minute")):
        trouves = [q for q in ids if motif in q]
        if trouves:
            return typ, next((limites[q] for q in trouves if q in limites), None)
    return "429_inconnu", None


def classer_erreur(e) -> tuple[str, int | None]:
    """(type d'erreur, limite annoncée par Google ou None)."""
    if _est_429(e):
        return _classer_429(str(e))
    msg = str(e).lower()
    if "api_key" in msg and "invalid" in msg:
        return "clé_invalide", None
    if "503" in msg or "unavailable" in msg:
        return "service_unavailable", None
    return "inconnu", None


def pause_minute(e, tentative: int, seuil: int) -> int | None:
    """429 par minute : attente demandée par Google (retryDelay) si elle est
    ≤ seuil, pour une seule nouvelle tentative (au premier essai). Sinon None :
    pas de nouvel essai, l'appelant passe à son repli (Groq).
    +1 s : Google arrondit retryDelay à la seconde inférieure (12,27 s → « 12s »)."""
    m = _RETRY_DELAY.search(str(e))
    if tentative > 1 or not m or int(m[1]) > seuil:
        return None
    return int(m[1]) + 1


def message_erreur(typ: str, limite: int | None, brut: str) -> str:
    """Texte court pour error_message ; le chiffre éventuel est celui de Google."""
    if typ == "quota_quotidien":
        return "Quota Gemini quotidien atteint" + (f" ({limite} requêtes/jour selon Google)" if limite else "")
    if typ == "rate_limit_minute":
        return "Rate limit Gemini par minute" + (f" ({limite} requêtes/min selon Google)" if limite else "")
    if typ == "429_inconnu":
        return "Gemini 429 sans identifiant de quota"
    if typ == "clé_invalide":
        return "Clé Gemini invalide"
    if typ == "service_unavailable":
        return "Service Gemini momentanément indisponible (503)"
    return brut[:200] or "?"
