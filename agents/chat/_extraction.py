"""
agents/chat/_extraction.py — Extraction des tickers + fallback yfinance (v5.4.2).
Phase 4 / E2 : mots entiers, majuscules d'origine hors watchlist, ordre déterministe.
Isolé du context_builder pour respecter la limite de 200 lignes.
"""

import re
from utils.helpers import charger_watchlist, tous_les_tickers


# Noms d'entreprises courants → tickers (extensible facilement)
NOMS_VERS_TICKERS = {
    "tesla": "TSLA", "apple": "AAPL", "nvidia": "NVDA", "microsoft": "MSFT",
    "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL", "meta platforms": "META",
    "facebook": "META", "netflix": "NFLX", "disney": "DIS", "boeing": "BA",
    "ford": "F", "vertiv": "VRT", "amd": "AMD", "intel": "INTC", "micron": "MU",
    "vistra": "VST", "constellation energy": "CEG", "lumentum": "LITE",
    "applied materials": "AMAT",
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD",
    "cardano": "ADA-USD", "ripple": "XRP-USD", "hbar": "HBAR-USD",
    "hedera": "HBAR-USD", "cronos": "CRO-USD", "cro": "CRO-USD",
    "l'or": "GC=F", "l’or": "GC=F", "gold": "GC=F", "pétrole": "CL=F", "petrole": "CL=F",
    "nasdaq": "NQ=F", "sp500": "SPY", "s&p": "SPY", "qqq": "QQQ",
}

# Phase 4 / E2 : tickers de la watchlist qui sont aussi des mots courants
# (FR / PT / EN) → reconnus seulement s'ils sont tapés en MAJUSCULES.
# sol (FR sol, PT soleil), spy (EN espion), voo (PT vol), lite (EN), cl (centilitre).
# La forme complète (sol-usd, cl=f) et les noms (solana, pétrole…) restent toute casse.
MAJUSCULES_SEULEMENT = {"SOL", "SPY", "VOO", "LITE", "CL"}

# Phase 4 / E2 : appliquée à la question D'ORIGINE (jamais après .upper()) —
# un ticker hors watchlist n'est retenu que s'il est tapé en majuscules.
# (?<!\w) / (?!\w) : bornes de mot Unicode (é, ô… comptent comme des lettres).
_RE_TICKER_MAJ = re.compile(r"(?<!\w)([A-Z]{2,5}(?:-USD)?(?:=F)?(?:=X)?)(?!\w)")

_STOP_WORDS_UPPER = {
    # Articles / pronoms / déterminants FR
    "LE", "LA", "DE", "UN", "UNE", "CE", "MA", "MON", "TON", "SES", "SON", "SA",
    "MES", "TES", "NOS", "VOS", "LES", "DES", "DU", "AU", "AUX", "CET", "CETTE",
    "JE", "TU", "IL", "ELLE", "NOUS", "VOUS", "ILS", "ELLES", "ON", "SE", "TE",
    "ME", "LEUR", "LUI", "MOI", "TOI", "SOI", "EUX", "CEUX", "CELUI",
    # Verbes / adverbes / conjonctions
    "SUIS", "ES", "EST", "SONT", "AI", "AS", "AVONS", "AVEZ", "ONT", "ETE", "ETRE",
    "VA", "VAS", "VONT", "ALLEZ", "ALLONS", "IRA", "IRAI", "IRAS", "IRONS",
    "FAIS", "FAIT", "FONT", "FERA", "FERAI", "FERAS", "FERONS", "PEUX", "PEUT",
    "DOIS", "DOIT", "DEVAIT", "DEVRA", "DIS", "DIT", "DIRE", "VEUX", "VEUT",
    "EN", "Y", "DONC", "OR", "NI", "MAIS", "CAR", "QUE", "QUOI", "QUEL", "QUELS",
    "QUELLE", "QUI", "OU", "SI", "ET", "PUIS", "AUSSI", "ENCORE", "TOUJOURS",
    "JAMAIS", "SOUVENT", "PARFOIS", "MAINTENANT", "AVANT", "APRES", "PENDANT",
    "OUI", "NON", "PAS", "PLUS", "MOINS", "TRES", "TROP", "BIEN", "MAL", "PEU",
    "TOUT", "TOUS", "TOUTE", "TOUTES", "MEME", "MEMES", "AUTRE", "AUTRES",
    "SUR", "DANS", "AVEC", "POUR", "PAR", "SANS", "SOUS", "HORS", "CHEZ", "VERS",
    "ENTRE", "PARMI", "SELON", "MALGRE", "GRACE",
    # Techniques / acronymes (pas des tickers)
    "OK", "USA", "URL", "API", "PDF", "CSV", "JSON", "HTML", "SQL", "CRM",
    "CEO", "CFO", "IPO", "ETF", "SL", "TP", "RR", "AI", "IA", "LLM", "MCP",
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY", "HKD",
    "FED", "BCE", "ECB", "FMI", "IMF", "PIB", "GDP", "CPI", "PPI", "PMI",
    "RSI", "MACD", "EMA", "SMA", "ATR", "ADX", "VWAP", "OHLC", "OHLCV",
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "STOP", "LOSS", "GAIN", "PROFIT",
    "NEW", "TOP", "MAX", "MIN", "AVG", "SUM", "END",
}


def _mot_entier(terme: str, casse_exacte: bool = False) -> re.Pattern:
    """Terme sur mot entier (« clôture » ≠ « cl »), insensible à la casse par défaut."""
    return re.compile(rf"(?<!\w){re.escape(terme.strip())}(?!\w)",
                      0 if casse_exacte else re.IGNORECASE)


def extraire_tickers(question: str) -> list[str]:
    """
    Tickers cités dans la question, dans un ordre déterministe (Phase 4 / E2) :
      1. tickers de la watchlist, quelle que soit la casse, sur mot entier
         (« amat » → AMAT ; « macro » ne déclenche plus CRO-USD) — sauf
         MAJUSCULES_SEULEMENT (mots courants : « le sol » ≠ SOL) ;
      2. noms d'entreprises connus (NOMS_VERS_TICKERS), sur mot entier ;
      3. tickers hors watchlist, seulement s'ils sont tapés en MAJUSCULES.
    Tri : watchlist d'abord, puis ordre d'apparition dans la question.
    """
    trouves: dict[str, int] = {}  # ticker → 1re position dans la question

    def _noter(ticker: str, pos: int) -> None:
        trouves[ticker] = min(pos, trouves.get(ticker, pos))

    try:
        watchlist = tous_les_tickers(charger_watchlist())
    except Exception:
        watchlist = []
    par_base = {t.split("-")[0].split("=")[0]: t for t in watchlist}

    for t in watchlist:
        base = t.split("-")[0].split("=")[0]
        for terme in {t, base}:
            exacte = terme == base and base in MAJUSCULES_SEULEMENT
            m = _mot_entier(terme, casse_exacte=exacte).search(question)
            if m:
                _noter(t, m.start())

    for nom, ticker in NOMS_VERS_TICKERS.items():
        m = _mot_entier(nom).search(question)
        if m:
            _noter(ticker, m.start())

    for m in _RE_TICKER_MAJ.finditer(question):
        tk = m.group(1)
        core = re.sub(r"(-USD|=F|=X)$", "", tk)
        if core not in _STOP_WORDS_UPPER:
            _noter(par_base.get(tk, tk), m.start())  # « BTC » → BTC-USD, pas un doublon

    dans_watchlist = set(watchlist)
    return sorted(trouves, key=lambda t: (t not in dans_watchlist, trouves[t]))


def get_asset_a_la_volee(ticker: str) -> dict:
    """Fallback yfinance pour un actif hors watchlist. Retourne un dict robuste."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="3mo", interval="1d")
        if hist.empty:
            return {"found": False, "note": f"Aucune donnée yfinance pour {ticker}."}
        close = hist["Close"]
        current = float(close.iloc[-1])
        sma20 = float(close.iloc[-20:].mean()) if len(close) >= 20 else None
        sma50 = float(close.iloc[-50:].mean()) if len(close) >= 50 else None
        change_1m = (float((close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100)
                     if len(close) >= 21 else None)
        rsi = None
        try:
            delta = close.diff()
            gain  = delta.where(delta > 0, 0).rolling(14).mean()
            loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
            if loss.iloc[-1] and loss.iloc[-1] > 0:
                rs = gain.iloc[-1] / loss.iloc[-1]
                rsi = round(100 - 100 / (1 + rs), 1)
        except Exception:
            pass
        market_cap = None
        try:
            market_cap = getattr(t.fast_info, "market_cap", None)
        except Exception:
            pass
        return {
            "found": True, "source": "yfinance (hors watchlist)",
            "prix":   round(current, 4),
            "rsi":    rsi,
            "sma20":  round(sma20, 2) if sma20 else None,
            "sma50":  round(sma50, 2) if sma50 else None,
            "change_1m_pct": round(change_1m, 1) if change_1m else None,
            "market_cap":    market_cap,
        }
    except Exception as e:
        return {"found": False, "error": str(e)[:150]}
