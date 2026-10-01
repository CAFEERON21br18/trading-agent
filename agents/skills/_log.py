"""
agents/skills/_log.py — Journal d'auto-apprentissage des biais (v5.3.9).
Chaque exécution du skill métacognition logge les biais détectés dans
memory/metacognition_log.md. Sert à identifier les biais récurrents
de l'agent au fil du temps.
"""

import os
from datetime import datetime, timezone

from utils.audit_trace import noter_ecriture

_MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "memory"
)
_LOG_FILE = os.path.join(_MEMORY_DIR, "metacognition_log.md")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def initialiser_log() -> None:
    """Crée le fichier s'il n'existe pas."""
    if os.path.exists(_LOG_FILE):
        return
    os.makedirs(_MEMORY_DIR, exist_ok=True)
    with open(_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("# Journal de métacognition — biais détectés\n\n"
                "Auto-mis à jour à chaque décision auditée. Sert à identifier "
                "les biais récurrents.\n\n")


def logger_audit(ticker: str, decision: str, audit: dict) -> None:
    """Append d'un audit métacognitif. audit = sortie du skill metacognition."""
    if not audit or not audit.get("disponible"):
        return
    try:
        initialiser_log()
        verdict   = audit.get("verdict", "?")
        score     = audit.get("score_solidite", "?")
        biais     = audit.get("biais_detectes", []) or []
        angles    = audit.get("angles_morts", []) or []
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {_now_iso()} — {ticker} ({decision})\n")
            f.write(f"**Verdict** : {verdict} (solidité {score}/10)\n")
            if biais:
                f.write("**Biais détectés** :\n")
                for b in biais:
                    nom = b.get("biais", "?") if isinstance(b, dict) else str(b)
                    ind = b.get("indice", "")  if isinstance(b, dict) else ""
                    f.write(f"- {nom}" + (f" — {ind}" if ind else "") + "\n")
            if angles:
                f.write("**Angles morts** :\n")
                for a in angles[:3]:
                    f.write(f"- {a}\n")
        # Audit du chat (Phase 4) : écriture mémoire déclenchée par un message ?
        noter_ecriture("fichier", "memory/metacognition_log.md", "APPEND")
    except Exception:
        pass  # le log ne doit JAMAIS bloquer une décision
