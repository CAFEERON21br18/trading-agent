"""
agents/technical_skills/economic_calendar.py — Skill 5 : calendrier économique.

Prochains événements à surveiller :
- Earnings des tickers suivis (via yfinance)
- FOMC (dates connues d'avance, hardcodées)
- CPI / NFP (dates récurrentes : NFP = 1er vendredi du mois, CPI = mi-mois)

Python pur + yfinance. Aucun LLM.
"""

import sys
import os
from datetime import datetime, date, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Dates FOMC (info publique fed.gov) — mettre à jour annuellement ─────────
FOMC_DATES = [
    date(2026,  1, 28), date(2026,  3, 18), date(2026,  4, 29),
    date(2026,  6, 17), date(2026,  7, 29), date(2026,  9, 16),
    date(2026, 11,  4), date(2026, 12, 16),
    date(2027,  1, 27), date(2027,  3, 17), date(2027,  4, 28),
    date(2027,  6, 16), date(2027,  7, 28), date(2027,  9, 22),
    date(2027, 11,  3), date(2027, 12, 15),
]


def _premier_vendredi(annee: int, mois: int) -> date:
    """1er vendredi d'un mois = date NFP (Non-Farm Payrolls)."""
    d = date(annee, mois, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def evenements_macro(jours_avant: int = 30) -> list[dict]:
    """Retourne les événements macro dans les N prochains jours (FOMC, CPI, NFP)."""
    aujourdhui = datetime.now(timezone.utc).date()
    limite = aujourdhui + timedelta(days=jours_avant)
    evts = []

    for d in FOMC_DATES:
        if aujourdhui <= d <= limite:
            evts.append({"type": "FOMC", "date": d.isoformat(),
                          "impact": "high", "delta_jours": (d - aujourdhui).days,
                          "detail": "Décision Fed sur les taux"})

    # CPI approximé (2e semaine) et NFP (1er vendredi) sur les 2 prochains mois
    for offset in range(3):
        m = aujourdhui.month + offset
        y = aujourdhui.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        try:
            nfp = _premier_vendredi(y, m)
            if aujourdhui <= nfp <= limite:
                evts.append({"type": "NFP", "date": nfp.isoformat(),
                              "impact": "high", "delta_jours": (nfp - aujourdhui).days,
                              "detail": "Non-Farm Payrolls (emploi US)"})
            cpi = date(y, m, 12)  # approximation
            if aujourdhui <= cpi <= limite:
                evts.append({"type": "CPI", "date": cpi.isoformat(),
                              "impact": "high", "delta_jours": (cpi - aujourdhui).days,
                              "detail": "Inflation US (approx mi-mois)"})
        except Exception:
            pass

    return sorted(evts, key=lambda e: e["date"])


def prochains_earnings(ticker: str, jours_avant: int = 30) -> dict | None:
    """Récupère la prochaine date d'earnings pour un ticker via yfinance."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        if not cal:
            return None
        earn = cal.get("Earnings Date")
        if not earn:
            return None
        # earn peut être une liste [date] ou une date directe
        d = earn[0] if isinstance(earn, list) else earn
        if isinstance(d, datetime):
            d = d.date()
        aujourdhui = datetime.now(timezone.utc).date()
        delta = (d - aujourdhui).days
        if delta < 0 or delta > jours_avant:
            return None
        return {
            "type":         "earnings",
            "asset":        ticker,
            "date":         d.isoformat(),
            "delta_jours":  delta,
            "impact":       "high" if delta <= 3 else "medium",
            "detail":       (f"Earnings dans {delta}j. Consensus EPS "
                              f"{cal.get('Earnings Average', 'N/A')}"),
        }
    except Exception as e:
        logger.warning(f"prochains_earnings({ticker}) : {e}")
        return None


def evenements_a_surveiller(tickers: list[str], jours_avant: int = 7) -> dict:
    """Résumé : macro + earnings pour la watchlist. Cache-friendly."""
    macro = evenements_macro(jours_avant)
    earnings = []
    for t in tickers[:20]:  # limite pour éviter trop d'appels yfinance
        e = prochains_earnings(t, jours_avant)
        if e:
            earnings.append(e)
    return {
        "macro":       macro,
        "earnings":    sorted(earnings, key=lambda e: e["delta_jours"]),
        "total":       len(macro) + len(earnings),
        "horizon_j":   jours_avant,
    }


def alerte_evenement_proche(ticker: str, seuil_jours: int = 3) -> str | None:
    """Retourne un warning si un événement à fort impact touche l'actif <= seuil jours."""
    e = prochains_earnings(ticker, jours_avant=seuil_jours)
    if e:
        return (f"⚠️ Earnings {ticker} dans {e['delta_jours']}j — volatilité "
                f"attendue. Réduire la taille ou attendre.")
    macro = [m for m in evenements_macro(seuil_jours) if m["delta_jours"] <= seuil_jours]
    if macro:
        m = macro[0]
        return (f"⚠️ {m['type']} dans {m['delta_jours']}j — événement macro à "
                f"fort impact sur le marché.")
    return None
