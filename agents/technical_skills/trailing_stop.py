"""
agents/technical_skills/trailing_stop.py — Skill 2 : trailing stop intelligent.

Stop-loss qui suit le prix pour sécuriser les gains, sans jamais redescendre.
- Basé sur l'ATR pour s'adapter à la volatilité de chaque actif
- LONG  : trailing = max(existant, prix - k*ATR)
- SHORT : trailing = min(existant, prix + k*ATR)
- Opt-in par position (colonne trailing_stop_active)

Python pur, aucun appel LLM.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger   import get_logger
from utils.database import get_connection
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs

logger = get_logger(__name__)

DEFAULT_ATR_MULTIPLIER = 2.0
MIN_UPTICK_PCT = 0.001  # 0.1% de bougé mini pour économiser un UPDATE


def calculer_atr(ticker: str, timeframe: str = "1d") -> float | None:
    """Retourne l'ATR(14) le plus récent pour ce ticker, ou None."""
    try:
        df = charger_ohlcv(ticker, timeframe, limite=60)
        if df.empty or len(df) < 14:
            return None
        df = calculer_tous_indicateurs(df)
        atr = df.iloc[-1].get("atr")
        return float(atr) if atr is not None and str(atr) != "nan" else None
    except Exception as e:
        logger.warning(f"calculer_atr({ticker}) : {e}")
        return None


def calculer_trailing_stop(entry_price: float, current_price: float,
                            direction: str, atr: float,
                            atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
                            current_ts: float | None = None) -> float:
    """Calcule le trailing stop selon la direction. Ne descend jamais (LONG),
    ne monte jamais (SHORT)."""
    marge = atr_multiplier * atr
    if direction == "LONG":
        candidat = current_price - marge
        # Initialisation à partir du prix d'entrée
        base = entry_price - marge if current_ts is None else current_ts
        return round(max(candidat, base), 6)
    # SHORT
    candidat = current_price + marge
    base = entry_price + marge if current_ts is None else current_ts
    return round(min(candidat, base), 6)


def activer_trailing_stop(position_id: int,
                          atr_multiplier: float = DEFAULT_ATR_MULTIPLIER) -> dict:
    """Active le trailing sur une position et initialise le prix stop.
    Retourne {ok: bool, initial_stop: float, atr: float, ...}."""
    conn = get_connection()
    pos = conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
    if not pos:
        conn.close()
        return {"ok": False, "error": "position introuvable"}
    if pos["status"] != "OPEN":
        conn.close()
        return {"ok": False, "error": f"position pas ouverte (status={pos['status']})"}
    atr = calculer_atr(pos["ticker"])
    if atr is None or atr <= 0:
        conn.close()
        return {"ok": False, "error": "ATR indispo ou nul"}
    initial = calculer_trailing_stop(pos["entry_price"], pos["entry_price"],
                                       pos["direction"], atr, atr_multiplier)
    conn.execute(
        "UPDATE positions SET trailing_stop_active=1, trailing_stop_price=?, "
        "atr_multiplier=? WHERE id=?",
        (initial, atr_multiplier, position_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Trailing activé sur #{position_id} ({pos['ticker']}) : "
                f"stop initial {initial} (ATR {atr:.4f} × {atr_multiplier})")
    return {"ok": True, "initial_stop": initial, "atr": round(atr, 6),
            "atr_multiplier": atr_multiplier}


def desactiver_trailing_stop(position_id: int) -> dict:
    """Désactive sans effacer les valeurs (traçabilité)."""
    conn = get_connection()
    conn.execute("UPDATE positions SET trailing_stop_active=0 WHERE id=?", (position_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "deactivated": True}


def mettre_a_jour_trailing_stop(position: dict, prix_actuel: float) -> dict | None:
    """Recalcule et met à jour en BDD si la nouvelle valeur est plus favorable.
    Retourne {ancien, nouveau, atr} si mise à jour, sinon None."""
    if not position.get("trailing_stop_active"):
        return None
    if prix_actuel is None or prix_actuel <= 0:
        return None
    ancien = position.get("trailing_stop_price")
    if ancien is None:
        return None
    atr = calculer_atr(position["ticker"])
    if atr is None or atr <= 0:
        return None
    k = position.get("atr_multiplier") or DEFAULT_ATR_MULTIPLIER
    nouveau = calculer_trailing_stop(
        position["entry_price"], prix_actuel, position["direction"],
        atr, k, current_ts=ancien,
    )
    # Ne rien faire si le changement est trop petit (ou pas favorable)
    delta = nouveau - ancien
    if abs(delta) < ancien * MIN_UPTICK_PCT:
        return None
    if position["direction"] == "LONG" and nouveau <= ancien:
        return None
    if position["direction"] == "SHORT" and nouveau >= ancien:
        return None
    conn = get_connection()
    conn.execute("UPDATE positions SET trailing_stop_price=? WHERE id=?",
                  (nouveau, position["id"]))
    conn.commit()
    conn.close()
    return {"ancien": ancien, "nouveau": nouveau, "atr": round(atr, 6),
            "delta": round(delta, 6)}


def touche_trailing(position: dict, prix_actuel: float) -> bool:
    """LONG : True si prix ≤ trailing. SHORT : True si prix ≥ trailing."""
    if not position.get("trailing_stop_active"):
        return False
    ts = position.get("trailing_stop_price")
    if ts is None or prix_actuel is None:
        return False
    if position["direction"] == "LONG":
        return prix_actuel <= ts
    return prix_actuel >= ts
