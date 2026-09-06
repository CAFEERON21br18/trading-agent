"""
agents/technical_skills/market_regime.py — Skill 1 : détection du régime de marché.

Règles de classification (par actif) :
    ADX > 25 + prix > EMA200 + EMA50 > EMA200 → HAUSSIER
    ADX > 25 + prix < EMA200 + EMA50 < EMA200 → BAISSIER
    ADX < 20                                    → RANGE
    20 ≤ ADX ≤ 25                              → TRANSITION

Régime global : combinaison SPY + BTC-USD → risk_on / risk_off / mixte.
Python pur (pandas-ta), aucun appel LLM.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger   import get_logger
from utils.database import get_connection
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs

logger = get_logger(__name__)


def detecter_regime_actif(ticker: str, timeframe: str = "1d") -> dict:
    """Retourne {regime, adx, ema_50, ema_200, prix, detail} pour un ticker.
    regime ∈ {haussier, baissier, range, transition, indispo}."""
    try:
        df = charger_ohlcv(ticker, timeframe, limite=250)
        if df.empty or len(df) < 200:
            return {"regime": "indispo", "adx": None, "detail": f"< 200 bougies {timeframe}"}
        df = calculer_tous_indicateurs(df)
        derniere = df.iloc[-1]
        adx     = _f(derniere.get("adx"))
        ema_50  = _f(derniere.get("ema_50"))
        ema_200 = _f(derniere.get("ema_200"))
        prix    = _f(derniere.get("Close"))
        if None in (adx, ema_50, ema_200, prix):
            return {"regime": "indispo", "adx": adx, "detail": "indicateurs manquants"}

        if adx < 20:
            regime = "range"
            detail = f"ADX {adx:.1f} < 20 → pas de tendance"
        elif 20 <= adx <= 25:
            regime = "transition"
            detail = f"ADX {adx:.1f} en zone grise 20-25"
        else:  # adx > 25
            if prix > ema_200 and ema_50 > ema_200:
                regime = "haussier"
                detail = f"ADX {adx:.1f} + prix > EMA200 + EMA50 > EMA200"
            elif prix < ema_200 and ema_50 < ema_200:
                regime = "baissier"
                detail = f"ADX {adx:.1f} + prix < EMA200 + EMA50 < EMA200"
            else:
                regime = "transition"
                detail = f"ADX {adx:.1f} fort mais EMAs non alignées"

        return {
            "regime":  regime,
            "adx":     round(adx, 2),
            "ema_50":  round(ema_50, 4),
            "ema_200": round(ema_200, 4),
            "prix":    round(prix, 4),
            "detail":  detail,
        }
    except Exception as e:
        logger.error(f"detecter_regime_actif({ticker}) : {e}")
        return {"regime": "indispo", "adx": None, "detail": str(e)[:120]}


def detecter_regime_global() -> dict:
    """Combine SPY + BTC-USD comme baromètres. Retourne
    {regime_global, regime_spy, regime_btc, mode: risk_on|risk_off|mixte, detail}."""
    r_spy = detecter_regime_actif("SPY")
    r_btc = detecter_regime_actif("BTC-USD")
    spy_r = r_spy.get("regime")
    btc_r = r_btc.get("regime")

    # Mode risk-on/off/mixte
    if spy_r == "haussier" and btc_r == "haussier":
        mode = "risk_on"
    elif spy_r == "baissier" and btc_r == "baissier":
        mode = "risk_off"
    elif spy_r in ("range", "transition") and btc_r in ("range", "transition"):
        mode = "indécis"
    else:
        mode = "mixte"

    # Régime global : le plus prudent des deux si mixte
    if spy_r == btc_r:
        regime_global = spy_r
    elif "baissier" in (spy_r, btc_r):
        regime_global = "baissier"  # asymétrie prudente
    elif "haussier" in (spy_r, btc_r):
        regime_global = "transition"
    else:
        regime_global = "range"

    return {
        "regime_global": regime_global,
        "regime_spy":    spy_r,
        "regime_btc":    btc_r,
        "mode":          mode,
        "adx_spy":       r_spy.get("adx"),
        "adx_btc":       r_btc.get("adx"),
        "detail":        f"SPY: {r_spy.get('detail','?')} | BTC: {r_btc.get('detail','?')}",
    }


def enregistrer_regime(scope: str, regime_info: dict) -> None:
    """Persiste dans market_regime. scope = 'global' ou ticker."""
    try:
        conn = get_connection()
        regime = regime_info.get("regime") or regime_info.get("regime_global") or "?"
        adx    = regime_info.get("adx") or regime_info.get("adx_spy")
        detail = regime_info.get("detail", "")
        conn.execute(
            "INSERT INTO market_regime (scope, regime, adx, detail, detected_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope, regime, adx, detail[:500],
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"enregistrer_regime({scope}) : {e}")


def dernier_regime(scope: str, max_age_heures: int = 24) -> dict | None:
    """Retourne le régime le plus récent pour le scope, ou None si > max_age."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT regime, adx, detail, detected_at FROM market_regime "
            "WHERE scope = ? ORDER BY detected_at DESC LIMIT 1",
            (scope,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        try:
            dt = datetime.fromisoformat(d["detected_at"].replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            d["age_heures"] = round(age_h, 1)
            if age_h > max_age_heures:
                return None
        except Exception:
            pass
        return d
    except Exception as e:
        logger.warning(f"dernier_regime({scope}) : {e}")
        return None


def _f(v) -> float | None:
    """Cast tolérant en float (gère NaN et None)."""
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except Exception:
        return None
