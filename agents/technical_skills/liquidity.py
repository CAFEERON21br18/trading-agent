"""
agents/technical_skills/liquidity.py — Skill 6 : analyse de liquidité.

Vérifie qu'un actif est assez liquide pour être tradé sans se retrouver
coincé (surtout petites cryptos). Filtre les entrées sur actifs peu liquides.

Python pur (pandas + BDD locale). Aucun LLM.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger    import get_logger
from utils.indicators import charger_ohlcv

logger = get_logger(__name__)

# Seuils de volume EN VALEUR ($ ou €) sur 20 jours par classe d'actif
SEUILS_VOLUME_QUOTIDIEN = {
    "crypto": 5_000_000,     # 5 M$/jour minimum
    "stock":  10_000_000,    # 10 M$/jour minimum
    "etf":    5_000_000,     # 5 M$/jour minimum
    "future": 100_000_000,   # 100 M$/jour (contrats à terme US)
    "forex":  None,          # forex = très liquide par nature
}


def _classe_actif(ticker: str) -> str:
    t = (ticker or "").upper()
    if t.endswith("-USD"): return "crypto"
    if t.endswith("=F"):   return "future"
    if t.endswith("=X"):   return "forex"
    if t in ("SPY", "QQQ", "VOO", "TLT", "GLD", "IWM"): return "etf"
    return "stock"


def analyser_liquidite(ticker: str, timeframe: str = "1d") -> dict:
    """Retourne {niveau, volume_moyen_20j, valeur_moyenne_$, classe, seuil,
    warning}. niveau ∈ {haute, correcte, faible, indispo}."""
    classe = _classe_actif(ticker)
    seuil  = SEUILS_VOLUME_QUOTIDIEN.get(classe)
    try:
        df = charger_ohlcv(ticker, timeframe, limite=25)
        if df.empty or len(df) < 5:
            return {"niveau": "indispo", "detail": "< 5 bougies", "classe": classe}
        recent = df.tail(20)
        vol_moyen = float(recent["Volume"].mean())
        prix_moyen = float(recent["Close"].mean())
        valeur_moyenne = vol_moyen * prix_moyen  # $ / jour
    except Exception as e:
        logger.warning(f"analyser_liquidite({ticker}) : {e}")
        return {"niveau": "indispo", "detail": str(e)[:120], "classe": classe}

    if classe == "forex":
        # forex = très liquide, on ne bloque pas
        return {
            "niveau":            "haute",
            "classe":            classe,
            "volume_moyen_20j":  round(vol_moyen, 0),
            "valeur_moyenne_$":  round(valeur_moyenne, 0),
            "seuil":             None,
            "warning":           None,
        }

    # Classification par ratio au seuil
    if seuil is None:
        niveau = "correcte"
    elif valeur_moyenne >= seuil * 3:
        niveau = "haute"
    elif valeur_moyenne >= seuil:
        niveau = "correcte"
    elif valeur_moyenne >= seuil * 0.3:
        niveau = "faible"
    else:
        niveau = "faible"  # < 30% du seuil = très faible

    warning = None
    if niveau == "faible":
        warning = (f"⚠️ Liquidité faible : {valeur_moyenne/1e6:.1f}M$/jour "
                   f"< seuil {seuil/1e6:.0f}M$/jour ({classe}). Slippage probable.")

    return {
        "niveau":            niveau,
        "classe":            classe,
        "volume_moyen_20j":  round(vol_moyen, 0),
        "valeur_moyenne_$":  round(valeur_moyenne, 0),
        "seuil":             seuil,
        "warning":           warning,
    }


def liquidite_suffisante(ticker: str) -> bool:
    """Helper booléen : True si niveau in {haute, correcte}."""
    r = analyser_liquidite(ticker)
    return r.get("niveau") in ("haute", "correcte")
