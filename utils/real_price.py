"""
utils/real_price.py — Récupération prix historique + actuel + calibration Revolut (v5.3)
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.database import get_connection

logger = get_logger(__name__)


# ── PARTIE 1 : Prix historique pour la saisie simplifiée ────────────────────

def get_historical_price(ticker: str, date_str: str, time_str: str | None = None) -> dict:
    """
    Récupère le prix d'un actif à une date (et heure) donnée.
    Si < 7j ET heure précise → intraday 15min. Sinon → clôture journalière.
    """
    import yfinance as yf
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            try:
                h, m = map(int, time_str.split(":"))
                target = target.replace(hour=h, minute=m)
            except Exception:
                time_str = None

        days_ago = (datetime.now() - target).days

        # Méthode 1 : intraday 15 min si récent + heure connue
        if days_ago <= 7 and time_str:
            try:
                data = yf.download(
                    ticker,
                    start=(target - timedelta(days=1)).strftime("%Y-%m-%d"),
                    end=(target + timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval="15m", progress=False, auto_adjust=False,
                )
                if not data.empty:
                    if data.index.tz is not None:
                        data.index = data.index.tz_localize(None)
                    closest = min(data.index, key=lambda x: abs((x - target).total_seconds()))
                    close = data.loc[closest, "Close"]
                    # gérer le cas où yfinance renvoie une Series multi-colonnes
                    if hasattr(close, "iloc"):
                        close = close.iloc[0]
                    return {
                        "price":       float(close),
                        "method":      "intraday_15m",
                        "actual_time": closest.strftime("%Y-%m-%d %H:%M"),
                        "note":        "Prix intraday précis (15 min)",
                    }
            except Exception as e:
                logger.warning(f"intraday {ticker} {date_str} : {e}")

        # Méthode 2 : clôture journalière
        try:
            data = yf.download(
                ticker,
                start=(target - timedelta(days=5)).strftime("%Y-%m-%d"),
                end=(target + timedelta(days=2)).strftime("%Y-%m-%d"),
                interval="1d", progress=False, auto_adjust=False,
            )
            if not data.empty:
                if data.index.tz is not None:
                    data.index = data.index.tz_localize(None)
                closest = min(data.index, key=lambda x: abs((x - target).days))
                close = data.loc[closest, "Close"]
                if hasattr(close, "iloc"):
                    close = close.iloc[0]
                note = "Clôture journalière"
                if days_ago > 7 and time_str:
                    note = "Clôture journalière (intraday dispo seulement 7 jours en arrière)"
                return {
                    "price":       float(close),
                    "method":      "daily_close",
                    "actual_time": closest.strftime("%Y-%m-%d"),
                    "note":        note,
                }
        except Exception as e:
            logger.warning(f"daily {ticker} {date_str} : {e}")

        return {"price": None, "error": "Aucune donnée pour cette date"}
    except Exception as e:
        logger.error(f"get_historical_price({ticker}) : {e}")
        return {"price": None, "error": str(e)}


# ── PARTIE 2 : Prix actuel le plus frais + calibration Revolut ─────────────

def get_current_price(ticker: str) -> dict:
    """
    Récupère le prix actuel le plus frais possible (sans calibration).
    Ordre : fast_info → info → 1m intraday → clôture.
    """
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)

        # 1. fast_info (le plus frais)
        try:
            fi = t.fast_info
            price = fi.get("lastPrice") if hasattr(fi, "get") else fi["lastPrice"]
            if price and float(price) > 0:
                return {"price": float(price), "source": "fast_info",
                        "timestamp": datetime.now().isoformat(timespec="seconds")}
        except Exception:
            pass

        # 2. info (inclut pre/post market)
        try:
            info = t.info
            for key in ("currentPrice", "regularMarketPrice", "preMarketPrice", "postMarketPrice"):
                v = info.get(key)
                if v and float(v) > 0:
                    return {"price": float(v), "source": key,
                            "timestamp": datetime.now().isoformat(timespec="seconds")}
        except Exception:
            pass

        # 3. dernière bougie 1 minute
        try:
            data = t.history(period="1d", interval="1m")
            if not data.empty:
                ts = data.index[-1]
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                return {"price": float(data["Close"].iloc[-1]),
                        "source": "intraday_1m",
                        "timestamp": ts.isoformat(timespec="seconds")}
        except Exception:
            pass

        # 4. clôture 5 jours (fallback)
        try:
            data = t.history(period="5d", interval="1d")
            if not data.empty:
                ts = data.index[-1]
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                return {"price": float(data["Close"].iloc[-1]),
                        "source": "daily_close",
                        "timestamp": ts.isoformat(timespec="seconds")}
        except Exception:
            pass

        return {"price": None, "error": "Aucun prix disponible"}
    except Exception as e:
        logger.error(f"get_current_price({ticker}) : {e}")
        return {"price": None, "error": str(e)}


def calibrate_to_revolut(ticker: str, revolut_price: float) -> dict:
    """Calibre le prix de l'agent sur celui affiché par Revolut."""
    base = get_current_price(ticker)
    agent_price = base.get("price")
    if not agent_price:
        return {"success": False, "error": "Prix agent indisponible"}

    factor = revolut_price / agent_price
    conn = get_connection()
    conn.execute("""
        INSERT INTO price_calibration (ticker, adjustment_factor, agent_price, revolut_price, calibrated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            adjustment_factor=excluded.adjustment_factor,
            agent_price=excluded.agent_price,
            revolut_price=excluded.revolut_price,
            calibrated_at=excluded.calibrated_at
    """, (ticker, factor, agent_price, revolut_price,
          datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    ecart = revolut_price - agent_price
    return {
        "success":           True,
        "agent_price":       round(agent_price, 4),
        "revolut_price":     revolut_price,
        "adjustment_factor": round(factor, 5),
        "note":              f"Écart de {abs(ecart):.2f}€ ({(factor-1)*100:+.2f}%) corrigé",
    }


def get_calibration(ticker: str) -> dict | None:
    """Retourne le facteur d'ajustement Revolut s'il existe pour ce ticker."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM price_calibration WHERE ticker = ?", (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_adjusted_price(ticker: str) -> dict:
    """Prix actuel AVEC facteur de calibration Revolut si configuré."""
    base = get_current_price(ticker)
    if not base.get("price"):
        return base
    cal = get_calibration(ticker)
    if cal and cal.get("adjustment_factor"):
        base["price_raw"]  = base["price"]
        base["price"]      = round(base["price"] * cal["adjustment_factor"], 4)
        base["calibrated"] = True
        base["adjustment_factor"] = cal["adjustment_factor"]
    else:
        base["calibrated"] = False
    return base


def prix_actuel_calibre(ticker: str) -> float | None:
    """Helper simple : retourne le prix calibré ou None.
    Réservé à l'affichage. Pour le P&L utiliser calculate_position_pnl."""
    r = get_adjusted_price(ticker)
    return r.get("price")


def prix_actuel_brut(ticker: str) -> float | None:
    """Helper simple : prix BRUT (non calibré) — référence pour le calcul du P&L."""
    r = get_current_price(ticker)
    return r.get("price")


def get_display_entry_price(ticker: str, entry_raw: float) -> float:
    """Prix d'entrée calibré pour l'affichage uniquement (≈ ce que Revolut affichait)."""
    cal = get_calibration(ticker)
    if cal and cal.get("adjustment_factor"):
        return round(entry_raw * cal["adjustment_factor"], 4)
    return entry_raw


def calculate_position_pnl(investment: dict, current_raw: float | None = None) -> dict | None:
    """
    v5.3.1 — Calcul P&L CORRECT : prix bruts cohérents (entrée brute + actuel brut).
    La calibration n'est utilisée que pour l'AFFICHAGE des prix unitaires.

    Math : le facteur s'annule dans le ratio → le % est identique en raw ou calibré.
    On garde le raw pour le calcul, et on affiche des prix calibrés pour la lisibilité.
    """
    ticker     = investment["asset"]
    entry_raw  = investment["entry_price"]
    quantity   = investment["quantity"]
    invested   = investment["invested_amount"]
    direction  = investment.get("direction", "LONG")

    if current_raw is None:
        info = get_current_price(ticker)
        current_raw = info.get("price")
        source = info.get("source")
    else:
        source = "cache"
    if not current_raw:
        return None

    # P&L : tout en prix BRUTS → cohérent et mathématiquement exact
    if direction == "LONG":
        pnl_euros = (current_raw - entry_raw) * quantity
    else:
        pnl_euros = (entry_raw - current_raw) * quantity
    pnl_percent   = (pnl_euros / invested * 100) if invested else 0.0
    current_value = invested + pnl_euros

    # Affichage : prix calibrés (pour ressembler à Revolut visuellement)
    cal = get_calibration(ticker)
    factor = cal["adjustment_factor"] if cal else 1.0
    entry_display   = round(entry_raw   * factor, 4)
    current_display = round(current_raw * factor, 4)

    return {
        "current_price_raw":      round(current_raw, 4),
        "current_price_display":  current_display,
        "entry_price_raw":        round(entry_raw, 4),
        "entry_price_display":    entry_display,
        "pnl_euros":              round(pnl_euros, 2),
        "pnl_percent":            round(pnl_percent, 2),
        "current_value":          round(current_value, 2),
        "calibrated":             cal is not None,
        "adjustment_factor":      factor,
        "source":                 source,
    }
