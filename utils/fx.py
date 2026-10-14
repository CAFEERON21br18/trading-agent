"""
utils/fx.py — Taux de change du portefeuille réel (D1, 14/10/2026).

Sert seulement là où des montants d'une position (devise de cotation) rencontrent
des euros (capital, budgets des plans). Les montants d'une position ne sont jamais
convertis pour eux-mêmes.

taux_eur(devise) → {taux, source, horodatage} : taux = unités de la devise pour
1 € (source « EURUSD=X » pour le dollar, cours yfinance du marché des changes,
pas le taux Revolut), horodatage = heure de la cotation. Montant en € = montant ÷ taux.
Échec de l'appel ou cours invalide → None, jamais 1.0 : l'affichage dit
« non disponible ». Un taux lu est gardé CACHE_S secondes ; un échec ne l'est pas.
"""

import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from utils.logger import get_logger
from utils.real_devise import DEVISE_DEFAUT

logger = get_logger(__name__)

CACHE_S = 300
NON_DISPO = "non disponible"
_cache: dict = {}


def _lire_yfinance(ticker: str) -> tuple[float, object] | None:
    """Dernière bougie horaire sur 5 jours : (cours, horodatage) ou None."""
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="5d", interval="1h")
    if h is None or h.empty:
        return None
    return float(h["Close"].iloc[-1]), h.index[-1]


def taux_eur(devise: str | None) -> dict | None:
    """Taux de `devise` pour 1 € ; None si indisponible (jamais 1.0 par défaut)."""
    d = (devise or DEVISE_DEFAUT).upper()
    if d == "EUR":
        return {"taux": 1.0, "source": "EUR, sans conversion", "horodatage": None}
    if len(d) != 3 or not d.isalpha():
        logger.warning(f"taux_eur : devise inconnue {d!r}")
        return None
    ticker = f"EUR{d}=X"
    garde = _cache.get(ticker)
    if garde and time.monotonic() - garde[0] < CACHE_S:
        return dict(garde[1])
    try:
        lu = _lire_yfinance(ticker)
    except Exception as e:
        logger.error(f"taux_eur({d}) : {ticker} illisible : {e}")
        return None
    if not lu or not math.isfinite(lu[0]) or lu[0] <= 0:
        logger.warning(f"taux_eur({d}) : aucun cours valide pour {ticker}")
        return None
    info = {"taux": lu[0], "source": ticker, "horodatage": lu[1].isoformat()}
    _cache[ticker] = (time.monotonic(), info)
    return dict(info)


def en_eur(montant: float, devise: str | None) -> tuple[float | None, dict | None]:
    """(montant en €, taux utilisé) ; (None, None) si le taux est indisponible."""
    info = taux_eur(devise)
    if info is None:
        return None, None
    return montant / info["taux"], info


def libelle_taux(info: dict | None) -> str:
    """« EURUSD=X 1,2500 (14/10 15h30) », « EUR, sans conversion » ou « non disponible »."""
    if info is None:
        return NON_DISPO
    if not info.get("horodatage"):
        return info["source"]
    heure = datetime.fromisoformat(info["horodatage"])
    try:
        heure = heure.astimezone(ZoneInfo(config.TIMEZONE))
    except Exception:
        pass  # heure de la cotation telle quelle
    taux = f"{info['taux']:.4f}".replace(".", ",")
    return f"{info['source']} {taux} ({heure:%d/%m %Hh%M})"
