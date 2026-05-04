"""
agents/explorers/screening_helpers.py — Filtres techniques mutualisés entre explorateurs
Chaque explorateur compose ces helpers selon ses spécificités.
"""

import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.indicators import calculer_tous_indicateurs
from utils.data_fetcher import recuperer_ohlcv_yf

logger = get_logger(__name__)


def ohlcv_df(ticker: str, periode: str = "3mo") -> pd.DataFrame:
    """Charge OHLCV via data_fetcher (cache 5 min) en DataFrame indexé."""
    rows = recuperer_ohlcv_yf(ticker, periode=periode, intervalle="1d")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = [c.capitalize() if c != "date" else c for c in df.columns]
    df["Date"] = pd.to_datetime(df["date"])
    df = df.set_index("Date")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def df_avec_indicateurs(ticker: str, periode: str = "6mo") -> pd.DataFrame:
    """Charge OHLCV + calcule tous les indicateurs."""
    df = ohlcv_df(ticker, periode)
    if df.empty or len(df) < 50:
        return df
    return calculer_tous_indicateurs(df)


# ── Filtres techniques génériques ───────────────────────────────────────────

def filtre_momentum(df: pd.DataFrame) -> tuple[bool, str]:
    """v4.1 : RSI > 50 + (MACD haussier OU prix > EMA20) — au lieu de tous obligatoires."""
    if df.empty or "rsi" not in df.columns:
        return False, ""
    d = df.iloc[-1]
    rsi, macd, sig, prix, ema20 = d.get("rsi"), d.get("macd"), d.get("macd_signal"), float(d["Close"]), d.get("ema_20")
    if rsi is None:
        return False, ""
    macd_haussier = (macd is not None and sig is not None and macd > sig)
    prix_au_dessus = (ema20 is not None and prix > ema20)
    if rsi > 50 and (macd_haussier or prix_au_dessus):
        details = f"RSI {rsi:.0f}"
        if macd_haussier: details += " + MACD haussier"
        if prix_au_dessus: details += " + prix > EMA20"
        return True, details
    return False, ""


def filtre_breakout(df: pd.DataFrame, periode: int = 20) -> tuple[bool, str]:
    """v4.1 : breakout 20j (avant 30j) + volume 1.3x (avant 1.5x) — détecte plus tôt."""
    if df.empty or len(df) < periode + 5:
        return False, ""
    prix = float(df["Close"].iloc[-1])
    high_n = float(df["High"].tail(periode).max())
    vol_actuel = float(df["Volume"].iloc[-1])
    vol_moyen  = float(df["Volume"].tail(periode).mean())
    if prix >= high_n * 0.99 and vol_actuel > vol_moyen * 1.3:
        return True, f"Breakout {periode}j + volume × {vol_actuel / max(vol_moyen, 1):.1f}"
    return False, ""


def filtre_volatilite_anormale(df: pd.DataFrame) -> tuple[bool, str]:
    """ATR récent > 1.5× moyenne ATR (signal de mouvement majeur)."""
    if df.empty or "atr" not in df.columns:
        return False, ""
    atr_recent = float(df["atr"].tail(5).mean())
    atr_moyen  = float(df["atr"].tail(50).mean()) if len(df) >= 50 else atr_recent
    if atr_moyen > 0 and atr_recent > 1.5 * atr_moyen:
        return True, f"Volatilité anormale (ATR récent × {atr_recent / atr_moyen:.1f})"
    return False, ""


def filtre_golden_cross(df: pd.DataFrame) -> tuple[bool, str]:
    """Croisement EMA50 au-dessus de EMA200 récemment."""
    if df.empty or "ema_50" not in df.columns or "ema_200" not in df.columns or len(df) < 5:
        return False, ""
    der  = df.iloc[-1]
    prev = df.iloc[-5]
    if (der["ema_50"] is None or der["ema_200"] is None or
        prev["ema_50"] is None or prev["ema_200"] is None):
        return False, ""
    cross_up = prev["ema_50"] <= prev["ema_200"] and der["ema_50"] > der["ema_200"]
    if cross_up:
        return True, "Golden cross EMA50/EMA200 (haussier long terme)"
    return False, ""


def filtre_death_cross(df: pd.DataFrame) -> tuple[bool, str]:
    """Croisement EMA50 sous EMA200 récemment (baissier)."""
    if df.empty or "ema_50" not in df.columns or "ema_200" not in df.columns or len(df) < 5:
        return False, ""
    der  = df.iloc[-1]
    prev = df.iloc[-5]
    if (der["ema_50"] is None or der["ema_200"] is None or
        prev["ema_50"] is None or prev["ema_200"] is None):
        return False, ""
    cross_dn = prev["ema_50"] >= prev["ema_200"] and der["ema_50"] < der["ema_200"]
    if cross_dn:
        return True, "Death cross EMA50/EMA200 (baissier long terme)"
    return False, ""


def appliquer_pack(df: pd.DataFrame, filtres: list, ticker: str = "") -> tuple[int, list[str]]:
    """
    Applique une liste de filtres et retourne (score, raisons).
    v4.1 — scoring plus généreux pour générer plus de découvertes :
      - Base : 4 si AU MOINS 1 filtre passe (avant 0)
      - +2 par filtre supplémentaire au-delà du 1er
      - +2 bonus si 3+ convergent
    Résultat : 1 filtre → 4, 2 → 6, 3 → 10, 4 → 12 (plafond 10).
    """
    raisons = []
    for fonction in filtres:
        try:
            ok, msg = fonction(df)
        except Exception as e:
            logger.error(f"Filtre {fonction.__name__} sur {ticker} : {e}")
            continue
        if ok:
            raisons.append(f"{fonction.__name__} : {msg}")
    n = len(raisons)
    if n == 0:
        return 0, []
    score = 4 + 2 * (n - 1)
    if n >= 3:
        score += 2
    return min(10, score), raisons
