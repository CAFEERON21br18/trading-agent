"""
utils/real_price_yahoo.py — Prix historique et prix actuel lus chez Yahoo (yfinance), sans calibration.
Sorti de utils/real_price.py (règle des 200 lignes) ; real_price.py le réexporte, et ses fonctions
(calibration, P&L) appellent get_current_price par son nom dans real_price.
"""

from datetime import datetime, timedelta

from utils.logger import get_logger

logger = get_logger("utils.real_price")  # même nom de journal qu'avant le découpage


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
