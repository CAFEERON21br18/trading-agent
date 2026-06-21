"""
agents/chat/chat_engine.py — Moteur du chat stratégique (v5.3.4)
Routage par intention → contexte structuré → enrichissement Gemini (fallback template).
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.database import get_connection
from agents.chat.context_builder import build_context
from agents.chat._formatters import formater_par_intention
from agents.chat._llm import enrichir_avec_gemini

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialiser_chat_db() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            context_used TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _detecter_intention(question: str) -> str:
    """Classifie la question pour router la construction du contexte."""
    q = question.lower()
    if any(k in q for k in ["paper", "papier", "comment se porte", "performance"]):
        return "paper_status"
    if any(k in q for k in ["réel", "réelle", "real", "mon portefeuille",
                             "mes positions réelles"]):
        return "real_status"
    if any(k in q for k in ["vendre", "vends", "sortir", "fermer", "couper"]):
        return "advice_sell"
    if any(k in q for k in ["acheter", "achète", "renforcer", "entrer", "investir"]):
        return "advice_buy"
    if any(k in q for k in ["pourquoi tu as", "explique"]):
        return "explain"
    if any(k in q for k in ["stratégie", "plan", "thèse", "opportun"]):
        return "strategy"
    if any(k in q for k in ["risque", "r:r", "ratio", "kelly", "drawdown"]):
        return "theory_risk"
    if any(k in q for k in ["macro", "économie", "fed", "taux", "récession"]):
        return "theory_macro"
    if any(k in q for k in ["btc", "bitcoin", "crypto", "marché crypto"]):
        return "market_crypto"
    return "general"


def repondre(question: str) -> dict:
    """Génère une réponse à partir de la question + contexte (+ Gemini si dispo)."""
    initialiser_chat_db()
    intention = _detecter_intention(question)
    contexte  = build_context(question)

    # 1. Construit la réponse template (fallback + matière première Gemini)
    template = formater_par_intention(intention, contexte)

    # 2. Enrichissement Gemini (graceful : retombe sur le template si KO)
    reponse, source = enrichir_avec_gemini(question, intention, template, contexte)
    logger.info(f"Chat [{intention}] source={source} ({len(reponse)} car.)")

    # 3. Historique
    try:
        conn = get_connection()
        conn.execute("INSERT INTO chat_history (role, message) VALUES (?, ?)",
                     ("user", question))
        conn.execute("INSERT INTO chat_history (role, message, context_used) "
                     "VALUES (?, ?, ?)", ("assistant", reponse, source))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Sauvegarde chat : {e}")

    return {"intention": intention, "reponse": reponse,
            "source": source, "timestamp": _now()}


def historique(limite: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


def vider_historique() -> bool:
    conn = get_connection()
    conn.execute("DELETE FROM chat_history")
    conn.commit()
    conn.close()
    return True
