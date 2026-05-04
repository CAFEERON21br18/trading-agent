"""
utils/data_fetcher.py — Wrapper unifié pour récupérer des données de marché mondiales
Couvre : crypto, actions, ETF, indices, forex, commodities, CFD via yfinance.
Ajoute la classification automatique du type d'actif et le cache.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.cache import avec_cache

logger = get_logger(__name__)

# ── Conventions de tickers yfinance par marché ───────────────────────────────
SUFFIXES_BOURSES = {
    ".PA": "Euronext Paris", ".AS": "Euronext Amsterdam", ".BR": "Euronext Bruxelles",
    ".LS": "Euronext Lisbonne", ".L": "LSE Londres", ".DE": "XETRA Frankfurt",
    ".SW": "SIX Suisse", ".MC": "BME Madrid", ".MI": "Borsa Italiana",
    ".ST": "OMX Stockholm", ".OL": "Oslo Børs", ".HE": "Helsinki",
    ".T": "Tokyo", ".HK": "HKEX Hong Kong", ".SS": "Shanghai", ".SZ": "Shenzhen",
    ".KS": "KRX Corée", ".KQ": "KOSDAQ", ".NS": "NSE Inde", ".BO": "BSE Inde",
    ".AX": "ASX Australie", ".SI": "SGX Singapour", ".TW": "Taiwan",
    ".SR": "Tadawul Arabie", ".JO": "JSE Afrique du Sud", ".TA": "TASE Israël",
    ".TO": "TSX Canada", ".SA": "B3 Brésil", ".MX": "BMV Mexique",
}

# Indices mondiaux courants (préfixés par ^ chez yfinance)
INDICES_MONDIAUX = {
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite", "^DJI": "Dow Jones 30",
    "^RUT": "Russell 2000", "^VIX": "VIX", "^FTSE": "FTSE 100",
    "^GDAXI": "DAX 40", "^FCHI": "CAC 40", "^IBEX": "IBEX 35",
    "^FTMIB": "FTSE MIB", "^SSMI": "SMI", "^AEX": "AEX", "^STOXX50E": "Euro Stoxx 50",
    "^N225": "Nikkei 225", "^HSI": "Hang Seng", "^KS11": "KOSPI",
    "^BSESN": "SENSEX", "^NSEI": "Nifty 50", "^AXJO": "ASX 200", "^TWII": "TAIEX",
}

# Commodities futures (suffixe =F)
COMMODITIES_FUTURES = {
    "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "PA=F": "Palladium",
    "CL=F": "Crude Oil WTI", "BZ=F": "Brent", "NG=F": "Natural Gas",
    "HG=F": "Copper", "ALI=F": "Aluminum", "ZW=F": "Wheat", "ZC=F": "Corn",
    "ZS=F": "Soybeans", "KC=F": "Coffee", "CC=F": "Cocoa", "SB=F": "Sugar",
    "CT=F": "Cotton", "ZR=F": "Rice", "NQ=F": "Nasdaq Futures", "ES=F": "S&P Futures",
}

# Forex (suffixe =X chez yfinance pour les paires)
FOREX_MAJEURS = {
    "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF", "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD", "EURGBP=X": "EUR/GBP", "EURJPY=X": "EUR/JPY",
}


def detecter_type(ticker: str) -> str:
    """Classifie un ticker : crypto / action / etf / indice / commodity / forex / cfd / inconnu."""
    t = ticker.upper()
    if t.endswith("-USD"):
        return "crypto"
    if t.startswith("^") or t in INDICES_MONDIAUX:
        return "indice"
    if t.endswith("=F") or t in COMMODITIES_FUTURES:
        return "commodity"
    if t.endswith("=X") or t in FOREX_MAJEURS:
        return "forex"
    for suf in SUFFIXES_BOURSES:
        if t.endswith(suf):
            return "action"
    if t in {"SPY", "QQQ", "VOO", "IWM", "VTI", "VXUS", "ARKK", "GLD", "SLV", "TLT"}:
        return "etf"
    return "action"  # par défaut, ticker court sans suffixe = US action


def recuperer_ohlcv_yf(ticker: str, periode: str = "1mo", intervalle: str = "1d") -> list[dict]:
    """
    Récupère OHLCV via yfinance. Cache 5 min.
    Retourne une liste de dicts [{date, open, high, low, close, volume}].
    """
    cle = f"{ticker}_{periode}_{intervalle}"

    def fetch():
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=periode, interval=intervalle)
        if hist.empty:
            return []
        rows = []
        for ts, row in hist.iterrows():
            rows.append({
                "date":   str(ts)[:19],
                "open":   float(row.get("Open", 0) or 0),
                "high":   float(row.get("High", 0) or 0),
                "low":    float(row.get("Low", 0) or 0),
                "close":  float(row.get("Close", 0) or 0),
                "volume": float(row.get("Volume", 0) or 0),
            })
        return rows

    return avec_cache("prix_ohlcv", cle, fetch) or []


def prix_actuel(ticker: str) -> float | None:
    """Dernier prix de clôture (court-circuit du cache si très récent)."""
    rows = recuperer_ohlcv_yf(ticker, periode="5d", intervalle="1d")
    return rows[-1]["close"] if rows else None


def info_actif(ticker: str) -> dict:
    """Métadonnées d'un actif : type détecté + nom + dernier prix."""
    type_ = detecter_type(ticker)
    nom = INDICES_MONDIAUX.get(ticker) or COMMODITIES_FUTURES.get(ticker) \
        or FOREX_MAJEURS.get(ticker) or ticker
    return {"ticker": ticker, "type": type_, "nom": nom, "prix": prix_actuel(ticker)}


def recuperer_lot(tickers: list[str], periode: str = "1mo", intervalle: str = "1d") -> dict:
    """Récupère les OHLCV pour plusieurs tickers (bulk avec cache par ticker)."""
    return {t: recuperer_ohlcv_yf(t, periode, intervalle) for t in tickers}
