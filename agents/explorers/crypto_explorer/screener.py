"""
agents/explorers/crypto_explorer/screener.py — Filtres pour le Crypto Explorer
Retourne (score 1-10, filtres déclenchés, détails) pour un ticker crypto.

Filtres implémentés (V1) :
1. VOLUME EXPLOSIF : volume 24h actuel >> moyenne récente
2. MOMENTUM : RSI 55-75 + MACD haussier + prix > EMA20
3. POTENTIEL FONDAMENTAL : market cap < 10B$ ET volume_24h > 5M$
4. ANOMALIE : chute > 15% sur top 50 (potentiel rebond)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pandas as pd
from utils.logger import get_logger
from utils.indicators import calculer_tous_indicateurs
from utils.data_fetcher import recuperer_ohlcv_yf

logger = get_logger(__name__)


def _filtre_momentum(df) -> tuple[bool, str]:
    """RSI 55-75 + MACD > MACD_signal + prix > EMA20."""
    if df.empty or "rsi" not in df.columns:
        return False, ""
    derniere = df.iloc[-1]
    rsi  = derniere.get("rsi")
    macd = derniere.get("macd")
    macd_sig = derniere.get("macd_signal")
    prix = float(derniere["Close"])
    ema_20 = derniere.get("ema_20")
    if rsi is None or macd is None or macd_sig is None or ema_20 is None:
        return False, ""
    if 55 <= rsi <= 75 and macd > macd_sig and prix > ema_20:
        return True, f"RSI {rsi:.0f} + MACD haussier + prix > EMA20"
    return False, ""


def _filtre_volume_explosif(df, meta: dict) -> tuple[bool, str]:
    """Volume CoinGecko 24h > 3× volume moyen 7j (yfinance)."""
    if df.empty or "Volume" not in df.columns:
        return False, ""
    vol_7j = df["Volume"].tail(7).mean()
    vol_24h = meta.get("volume_24h", 0)
    # On compare en valeur USD : (vol_24h coingecko) vs (vol_7j × prix yfinance)
    prix = float(df["Close"].iloc[-1])
    vol_7j_usd = vol_7j * prix
    if vol_7j_usd > 0 and vol_24h > 3 * vol_7j_usd:
        return True, f"Volume 24h {vol_24h/1e6:.1f}M$ vs moyenne 7j {vol_7j_usd/1e6:.1f}M$"
    return False, ""


def _filtre_potentiel_fonda(meta: dict) -> tuple[bool, str]:
    """Market cap < 10B$ ET volume > 5M$/jour."""
    mc = meta.get("market_cap", 0)
    vol = meta.get("volume_24h", 0)
    if 0 < mc < 10e9 and vol > 5e6:
        return True, f"Mid-cap (${mc/1e9:.1f}B) + bon volume (${vol/1e6:.1f}M)"
    return False, ""


def _filtre_anomalie(meta: dict) -> tuple[bool, str]:
    """Chute > 15% en 24h sur top 50 → possibilité de rebond technique."""
    var = meta.get("variation_24h", 0)
    rank = meta.get("rank")
    if rank is not None and rank <= 50 and var < -15:
        return True, f"Anomalie : -{abs(var):.1f}% en 24h sur top {rank}"
    return False, ""


def _ohlcv_df(ticker: str, periode: str = "3mo") -> "pd.DataFrame":
    """Récupère OHLCV via data_fetcher (cache 5 min) et convertit en DataFrame indexé."""
    rows = recuperer_ohlcv_yf(ticker, periode=periode, intervalle="1d")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = [c.capitalize() if c != "date" else c for c in df.columns]
    df["Date"] = pd.to_datetime(df["date"])
    df = df.set_index("Date")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def evaluer_crypto(ticker: str, meta: dict) -> tuple[int, list[str], dict]:
    """Évalue un ticker crypto et retourne (score, filtres déclenchés, détails)."""
    df = _ohlcv_df(ticker)
    df = calculer_tous_indicateurs(df) if not df.empty else df

    filtres = []
    score = 0
    details = {"market_cap": meta.get("market_cap"),
               "volume_24h": meta.get("volume_24h"),
               "variation_24h": meta.get("variation_24h"),
               "rank": meta.get("rank")}

    # Application des filtres
    for nom, fonction, args in [
        ("momentum",      _filtre_momentum,        (df,)),
        ("volume_explosif", _filtre_volume_explosif, (df, meta)),
        ("potentiel_fondamental", _filtre_potentiel_fonda, (meta,)),
        ("anomalie",      _filtre_anomalie,        (meta,)),
    ]:
        try:
            ok, raison = fonction(*args)
            if ok:
                filtres.append(f"{nom} : {raison}")
                score += 2  # +2 par filtre déclenché
        except Exception as e:
            logger.error(f"Filtre {nom} sur {ticker} : {e}")

    # Bonus si plusieurs filtres convergent
    if len(filtres) >= 3:
        score += 2

    score = min(10, max(0, score))
    return score, filtres, details
