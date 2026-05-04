"""
agents/trade_journalist/journalist.py — Sous-agent 6 : Trade Journalist
Enregistre chaque signal émis dans la BDD SQLite et dans trade_journal.md.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger   import get_logger
from utils.database import get_connection

logger = get_logger(__name__)

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JOURNAL_FILE    = os.path.join(BASE_DIR, "memory", "trade_journal.md")


def generer_signal_id() -> str:
    """Génère un ID auto-incrémenté pour chaque signal : SIG-001, SIG-002, etc."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM signals")
        n = cursor.fetchone()["n"]
        conn.close()
        return f"SIG-{n+1:04d}"
    except Exception as e:
        logger.error(f"Erreur génération ID signal : {e}")
        return f"SIG-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


def enregistrer_signal(ticker: str, direction: str, confiance: int,
                       prix_signal: float, stop_loss: float,
                       target_1: float, target_2: float,
                       timeframe: str, source_agents: str, raison: str) -> str:
    """
    Enregistre un signal en BDD et le journalise.
    Retourne le signal_id généré.
    """
    signal_id = generer_signal_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals
                (signal_id, ticker, direction, timeframe, confidence,
                 price_at_signal, stop_loss, target_1, target_2,
                 source_agents, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, ticker, direction, timeframe, confiance,
              prix_signal, stop_loss, target_1, target_2,
              source_agents, raison, timestamp))
        conn.commit()
        conn.close()
        logger.info(f"Signal {signal_id} enregistré : {ticker} {direction} ({confiance}/10)")
    except Exception as e:
        logger.error(f"Erreur enregistrement signal : {e}")
        return ""

    # Ajout dans le journal markdown
    ajouter_au_journal_md(signal_id, ticker, direction, confiance, prix_signal,
                          stop_loss, target_1, target_2, source_agents, raison, timestamp)
    return signal_id


def ajouter_au_journal_md(signal_id: str, ticker: str, direction: str,
                          confiance: int, prix_signal: float, stop_loss: float,
                          target_1: float, target_2: float, source_agents: str,
                          raison: str, timestamp: str):
    """Ajoute une entrée formatée au fichier memory/trade_journal.md."""
    entree = f"""
---
### {signal_id} — {timestamp}
- **Actif** : {ticker}
- **Direction** : {direction}
- **Confiance** : {confiance}/10
- **Signal émis par** : {source_agents}
- **Prix signal** : {prix_signal:,.4f}
- **Stop-loss** : {stop_loss:,.4f}
- **Target 1** : {target_1:,.4f}
- **Target 2** : {target_2:,.4f}
- **Raison** : {raison}
- **Résultat** : *en attente*
"""
    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(entree)
    except Exception as e:
        logger.error(f"Erreur écriture journal markdown : {e}")


def cloturer_signal(signal_id: str, prix_sortie: float, lecon: str = "") -> bool:
    """
    Met à jour le résultat d'un signal clôturé.
    Calcule P&L et durée automatiquement depuis les données BDD.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
        sig = cursor.fetchone()
        if not sig:
            logger.warning(f"Signal {signal_id} introuvable")
            conn.close()
            return False

        prix_entree = sig["price_at_signal"]
        direction   = sig["direction"]
        if direction == "LONG":
            pnl_pct = (prix_sortie - prix_entree) / prix_entree * 100
        else:
            pnl_pct = (prix_entree - prix_sortie) / prix_entree * 100

        correct = "OUI" if pnl_pct > 0 else ("NON" if pnl_pct < 0 else "PARTIEL")
        closed_at = datetime.now(timezone.utc).isoformat()

        # Calcul durée (approximatif — diff entre timestamps ISO)
        try:
            t_start = datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00"))
            t_end   = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            duree_h = int((t_end - t_start).total_seconds() / 3600)
            duree = f"{duree_h}h"
        except Exception:
            duree = "N/A"

        cursor.execute("""
            INSERT OR REPLACE INTO signal_results
                (signal_id, exit_price, pnl_pct, duration, correct, lesson, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, prix_sortie, pnl_pct, duree, correct, lecon, closed_at))
        conn.commit()
        conn.close()
        logger.info(f"Signal {signal_id} clôturé : {correct} ({pnl_pct:+.2f}%)")
        return True
    except Exception as e:
        logger.error(f"Erreur clôture signal : {e}")
        return False


def lister_signaux_recents(limite: int = 10) -> list[dict]:
    """Retourne les N derniers signaux émis (avec leurs résultats si disponibles)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, r.exit_price, r.pnl_pct, r.correct
            FROM signals s
            LEFT JOIN signal_results r ON s.signal_id = r.signal_id
            ORDER BY s.timestamp DESC
            LIMIT ?
        """, (limite,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Erreur lecture signaux : {e}")
        return []
