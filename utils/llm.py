"""
utils/llm.py — Helper LLM unifié (Gemini → Groq fallback) (v5.4.0).

Tous les modules qui ont besoin d'un LLM passent par ask_llm().
- Essaie Gemini d'abord (réutilise utils.gemini.ask_gemini_status,
  donc rate-limit local + retry 429 + détection précise des erreurs)
- Bascule sur Groq si Gemini échoue (quota, 429, 503, ...) — modèle
  configurable via GROQ_MODEL (.env), openai/gpt-oss-120b par défaut
- Mode "silent" pour les cycles auto (retourne text=None si tout KO)
- Mode "verbose" pour le chat (retourne une bannière d'erreur claire)
- v5.7 (audit Phase 4) : la réponse contient aussi `tentatives` (une entrée
  par fournisseur essayé, erreur brute masquée). Ajout rétrocompatible.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.secret_mask import masquer_secrets
from utils.audit_trace import noter_appel_llm
import config

logger = get_logger(__name__)

MODEL_GEMINI = "gemini-2.5-flash"
# v5.4.2 : llama-3.3-70b-versatile a été déprécié par Groq → bascule sur
# groq/compound-mini.
# v5.4.3 : compound-mini à son tour retiré par Groq (2e modèle mort en peu
# de temps) → le modèle n'est plus codé en dur, il vient de GROQ_MODEL
# (.env), avec openai/gpt-oss-120b comme valeur par défaut.
DEFAULT_MODEL_GROQ = "openai/gpt-oss-120b"

# Les modèles "raisonneurs" (gpt-oss) réfléchissent avant de répondre et ces
# tokens de raisonnement sont décomptés de max_tokens : un budget trop
# faible peut donc renvoyer un texte final vide alors que le modèle a bien
# produit une réponse (juste engloutie par le raisonnement). On leur impose
# reasoning_effort="low" (réponse plus directe) et un budget minimum.
GROQ_MIN_TOKENS_RAISONNEUR = 1024


def _modele_raisonneur(model: str) -> bool:
    """True pour les modèles Groq de la famille gpt-oss (raisonnement Harmony)."""
    return "gpt-oss" in model


def cle_groq() -> str | None:
    """Clé Groq de CE processus (chargée au démarrage : un dashboard lancé
    avant une modification de .env garde l'ancienne clé)."""
    return getattr(config, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")


def modele_groq() -> str:
    return getattr(config, "GROQ_MODEL", None) or os.getenv("GROQ_MODEL") or DEFAULT_MODEL_GROQ


def ask_llm(prompt: str, system: str | None = None,
             mode: str = "silent",
             temperature: float = 0.7,
             max_tokens: int | None = None) -> dict:
    """
    Appel LLM avec fallback automatique Gemini → Groq.

    Returns:
        {text: str|None, source: "gemini"|"groq"|None,
         error: str|None, retry_after_sec: int|None,
         tentatives: [{fournisseur, modele, ok, type_erreur, erreur, duree_ms}]}

    Si mode="verbose" et les deux LLM sont KO, text contient une
    bannière d'erreur en français (pas None).
    """
    tentatives = []
    debut = time.monotonic()
    g = _try_gemini(prompt, system, temperature, max_tokens)
    tentatives.append(_tentative("gemini", MODEL_GEMINI, g, debut))
    if g["text"]:
        return _conclure(g, "gemini", tentatives, prompt, system)

    logger.warning(f"Gemini KO ({g['error']}) → fallback Groq")
    debut = time.monotonic()
    q = _try_groq(prompt, system, temperature, max_tokens)
    tentatives.append(_tentative("groq", modele_groq(), q, debut))
    if q["text"]:
        return _conclure(q, "groq", tentatives, prompt, system)

    logger.error(f"Gemini ET Groq KO : {g['error']} | {q['error']}")
    if mode == "verbose":
        msg = (f"⚠️ Services IA temporairement indisponibles "
               f"(Gemini : {g['error']}, Groq : {q['error']}).")
        return _conclure({"text": msg, "error": "both_failed",
                          "retry_after_sec": g.get("retry_after_sec")},
                         None, tentatives, prompt, system)
    return _conclure({"text": None, "error": "both_failed",
                      "retry_after_sec": g.get("retry_after_sec")},
                     None, tentatives, prompt, system)


def _tentative(fournisseur: str, modele: str, r: dict, debut: float) -> dict:
    """Une entrée de `tentatives` : résultat d'un fournisseur, erreur brute masquée."""
    return {"fournisseur": fournisseur, "modele": modele, "ok": bool(r.get("text")),
            "type_erreur": r.get("error"), "erreur": masquer_secrets(r.get("erreur_brute")),
            "duree_ms": int((time.monotonic() - debut) * 1000)}


def _conclure(r: dict, source, tentatives: list, prompt, system) -> dict:
    """Format de retour historique + `tentatives` ; signale l'appel à l'audit
    du chat (no-op hors requête auditée)."""
    res = {"text": r.get("text"), "source": source, "error": r.get("error"),
           "retry_after_sec": r.get("retry_after_sec"), "tentatives": tentatives}
    noter_appel_llm("ask_llm", prompt, system, res, sum(t["duree_ms"] for t in tentatives))
    return res


def _try_gemini(prompt, system, temperature, max_tokens):
    """Réutilise ask_gemini_status existant (rate-limit + retry déjà gérés)."""
    from utils.gemini import ask_gemini_status
    res = ask_gemini_status(prompt, system=system, temperature=temperature,
                             max_output_tokens=max_tokens)
    return {"text": res["text"] if res["ok"] else None,
            "error": res.get("error_type"),
            "retry_after_sec": res.get("retry_after_sec"),
            "erreur_brute": res.get("error_message")}


def _try_groq(prompt, system, temperature, max_tokens):
    """Tente Groq (modèle configurable via GROQ_MODEL). Retourne {text, error, retry_after_sec}."""
    api_key = cle_groq()
    if not api_key:
        return {"text": None, "error": "clé_groq_manquante", "retry_after_sec": None}
    model = modele_groq()
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": model, "messages": messages, "temperature": temperature}
        if _modele_raisonneur(model):
            # Réponse directe plutôt qu'un raisonnement long, et budget garanti
            # même si l'appelant n'a pas demandé de max_tokens (ou trop peu).
            kwargs["reasoning_effort"] = "low"
            kwargs["max_tokens"] = max(max_tokens or 0, GROQ_MIN_TOKENS_RAISONNEUR)
        elif max_tokens:
            kwargs["max_tokens"] = max_tokens
        c = client.chat.completions.create(**kwargs)
        text = (c.choices[0].message.content or "").strip()
        if not text:
            # Un texte vide n'est jamais une réponse valide (ex. tout le budget
            # de tokens englouti par le raisonnement) — c'est un échec Groq.
            return {"text": None, "error": "reponse_vide_groq", "retry_after_sec": None}
        return {"text": text, "error": None, "retry_after_sec": None}
    except Exception as e:
        err = str(e).lower()
        brute = str(e)[:300]  # erreur d'origine, gardée pour l'audit (masquée en aval)
        if "401" in err or "invalid_api_key" in err or "authentication" in err:
            return {"text": None, "error": "clé_groq_invalide", "retry_after_sec": None,
                    "erreur_brute": brute}
        if "429" in err or "rate" in err:
            return {"text": None, "error": "rate_limit_groq", "retry_after_sec": 60,
                    "erreur_brute": brute}
        if "quota" in err:
            return {"text": None, "error": "quota_groq", "retry_after_sec": 3600,
                    "erreur_brute": brute}
        return {"text": None, "error": str(e)[:80], "retry_after_sec": None,
                "erreur_brute": brute}


def llm_disponible() -> dict:
    """Diagnostic rapide : quels providers sont configurés ?"""
    return {
        "gemini": bool(getattr(config, "GEMINI_API_KEY", None)),
        "groq":   bool(getattr(config, "GROQ_API_KEY", None)),
    }
