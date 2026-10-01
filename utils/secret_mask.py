"""
utils/secret_mask.py — Masquage des secrets avant stockage ou affichage (Phase 4).

Fonction unique et réutilisable : masquer_secrets(texte). Appliquée à TOUS
les champs texte du journal d'audit (message, contexte, prompt, réponse,
erreurs, chaîne de fallback…), pas seulement au prompt.

Deux protections cumulées :
1. Valeurs exactes : toute variable d'environnement dont le nom désigne un
   secret (…KEY, …TOKEN, …SECRET, …PASSWORD) est remplacée par ***NOM***.
2. Motifs : paramètres d'URL (apiKey=…), en-têtes Authorization / Bearer /
   x-api-key, formats de clés connus (Groq gsk_…, Google AIza…, sk-…).
"""

import hashlib
import os
import re

# Noms de variables sensibles : GEMINI_API_KEY, NEWSAPI_KEY, EMAIL_APP_PASSWORD…
# (PWD / OLDPWD = répertoire courant du shell, pas des secrets → non retenus)
_NOM_SECRET = re.compile(r"(^|_)[A-Z]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD)($|_)", re.IGNORECASE)
_LONGUEUR_MIN = 8  # en dessous : trop de faux positifs ("true", "587"…)

_MOTIFS = [
    # Paramètres d'URL : ?apiKey=…, &token=…, &key=… (ex. erreurs NewsAPI)
    (re.compile(r"(?i)([?&](?:api[_-]?key|apikey|key|token|access[_-]?token|"
                r"auth|password|pwd|secret)=)[^&\s'\"#]+"), r"\1***"),
    # En-têtes HTTP
    (re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?(?:bearer\s+|basic\s+|token\s+)?)"
                r"[A-Za-z0-9._~+/=\-]{8,}"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=\-]{8,}"), r"\1***"),
    (re.compile(r"(?i)(x-(?:goog-)?api-key['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    # Formats de clés connus
    (re.compile(r"\bgsk_[A-Za-z0-9]{16,}"), "gsk_***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "AIza***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-***"),
]


def _valeurs_secretes() -> list[tuple[str, str]]:
    """(nom, valeur) des variables d'environnement sensibles, les plus longues d'abord."""
    paires = [(nom, val) for nom, val in os.environ.items()
              if _NOM_SECRET.search(nom) and val and len(val) >= _LONGUEUR_MIN]
    return sorted(paires, key=lambda p: len(p[1]), reverse=True)


def masquer_secrets(texte):
    """Retourne le texte sans aucun secret. None reste None ; le reste devient str."""
    if texte is None:
        return None
    if not isinstance(texte, str):
        texte = str(texte)
    for nom, valeur in _valeurs_secretes():
        if valeur in texte:
            texte = texte.replace(valeur, f"***{nom}***")
    for motif, remplacement in _MOTIFS:
        texte = motif.sub(remplacement, texte)
    return texte


def empreinte_secret(valeur: str | None) -> str | None:
    """Empreinte courte non réversible (8 hex) : identifie une clé sans la révéler."""
    if not valeur:
        return None
    return hashlib.sha256(valeur.encode("utf-8")).hexdigest()[:8]
