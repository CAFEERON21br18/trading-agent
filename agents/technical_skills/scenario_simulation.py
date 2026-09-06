"""
agents/technical_skills/scenario_simulation.py — Skill 8 : what-if + stress tests.

Deux usages :
  1. Simuler un trade AVANT de le prendre (haussier/baissier/neutre + espérance)
  2. Stress-tester le portefeuille (BTC -30%, marché -15%, dollar +10%, ...)

Python pur, aucun LLM. Utilise les corrélations existantes.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger    import get_logger
from utils.portfolio_db import lire_positions_ouvertes
from agents.paper_trader.portfolio import prix_actuel
from agents.analysts.sentiment_analyst.analyst import calculer_correlation

logger = get_logger(__name__)


# ── PARTIE 1 — What-if sur un trade individuel ───────────────────────────

def simuler_trade(entry_price: float, stop_loss: float,
                   target_1: float, target_2: float | None,
                   quantity: float, probabilite_reussite: float = 0.5) -> dict:
    """Simule 3 scénarios pour un trade. Retourne l'espérance mathématique.

    probabilite_reussite : 0.0-1.0, chance d'atteindre target_1
    (target_2 = 30% de la proba de target_1 par convention)"""
    p_tp1 = max(0.0, min(1.0, probabilite_reussite))
    p_tp2 = p_tp1 * 0.3 if target_2 else 0.0
    p_sl  = 1.0 - p_tp1  # simplification : soit on va jusqu'à target, soit on stoppe
    p_neutre = 0.0       # placeholder si on veut ajouter un scénario neutre

    gain_tp1 = (target_1 - entry_price) * quantity
    gain_tp2 = (target_2 - entry_price) * quantity if target_2 else 0
    perte_sl = (entry_price - stop_loss) * quantity  # positif = montant perdu

    esperance = (p_tp1 * gain_tp1) + (p_tp2 * (gain_tp2 - gain_tp1)) - (p_sl * perte_sl)
    return {
        "scenario_haussier_tp1": {
            "probabilite": round(p_tp1, 3),
            "prix":        target_1,
            "gain_euros":  round(gain_tp1, 2),
            "gain_pct":    round((target_1 / entry_price - 1) * 100, 2),
        },
        "scenario_haussier_tp2": {
            "probabilite": round(p_tp2, 3),
            "prix":        target_2,
            "gain_euros":  round(gain_tp2, 2) if target_2 else 0,
        } if target_2 else None,
        "scenario_baissier_sl": {
            "probabilite": round(p_sl, 3),
            "prix":        stop_loss,
            "perte_euros": round(-perte_sl, 2),
            "perte_pct":   round((stop_loss / entry_price - 1) * 100, 2),
        },
        "esperance_euros": round(esperance, 2),
        "esperance_positive": esperance > 0,
        "rr_ratio": round((target_1 - entry_price) / (entry_price - stop_loss), 2) if stop_loss < entry_price else None,
    }


# ── PARTIE 2 — Stress tests du portefeuille ──────────────────────────────

CHOCS_PREDEFINIS = {
    "btc_-30":       {"ref": "BTC-USD", "choc_pct": -30, "label": "BTC -30%"},
    "btc_-50":       {"ref": "BTC-USD", "choc_pct": -50, "label": "BTC -50%"},
    "marche_-15":    {"ref": "SPY",     "choc_pct": -15, "label": "Marché -15%"},
    "marche_-30":    {"ref": "SPY",     "choc_pct": -30, "label": "Marché -30% (crash)"},
    "dollar_+10":    {"ref": "SPY",     "choc_pct":  -5, "label": "Dollar +10% (proxy SPY -5%)"},
    "tech_-25":      {"ref": "QQQ",     "choc_pct": -25, "label": "Tech -25%"},
}


def _impact_estime(ticker: str, choc: dict) -> float:
    """Estime l'impact % d'un choc sur un ticker via corrélation."""
    if ticker == choc["ref"]:
        return choc["choc_pct"]
    try:
        c = calculer_correlation(ticker, choc["ref"], jours=60)
    except Exception:
        c = None
    if c is None:
        # Fallback prudent : 60% de sensibilité si pas de corrélation calculée
        return choc["choc_pct"] * 0.6
    # Impact = corrélation × choc du référentiel (simplification linéaire)
    return choc["choc_pct"] * c


def stress_test_portefeuille(choc_key: str = "marche_-15") -> dict:
    """Applique un choc défini à toutes les positions ouvertes. Retourne
    l'impact global attendu."""
    choc = CHOCS_PREDEFINIS.get(choc_key)
    if not choc:
        return {"error": f"choc inconnu ({choc_key})",
                "chocs_dispo": list(CHOCS_PREDEFINIS.keys())}
    positions = lire_positions_ouvertes()
    if not positions:
        return {"scenario": choc["label"], "positions_impactees": [],
                "impact_total_euros": 0, "impact_total_pct": 0,
                "invested_total": 0}

    invest_total = sum(p["invested_amount"] for p in positions)
    impacts = []
    perte_totale = 0.0
    for p in positions:
        pct = _impact_estime(p["ticker"], choc)
        px  = prix_actuel(p["ticker"])
        valeur_actuelle = (px or p["entry_price"]) * p["quantity"]
        perte_euros = valeur_actuelle * pct / 100
        perte_totale += perte_euros
        impacts.append({
            "ticker":       p["ticker"],
            "impact_pct":   round(pct, 2),
            "impact_euros": round(perte_euros, 2),
            "valeur_pre":   round(valeur_actuelle, 2),
            "valeur_post":  round(valeur_actuelle + perte_euros, 2),
        })

    valeur_actuelle_totale = sum(i["valeur_pre"] for i in impacts)
    return {
        "scenario":            choc["label"],
        "choc_key":            choc_key,
        "positions_impactees": impacts,
        "invested_total":      round(invest_total, 2),
        "valeur_actuelle":     round(valeur_actuelle_totale, 2),
        "impact_total_euros":  round(perte_totale, 2),
        "impact_total_pct":    round(perte_totale / valeur_actuelle_totale * 100, 2) if valeur_actuelle_totale else 0,
        "alerte":              (f"⚠️ Perte estimée {perte_totale/valeur_actuelle_totale*100:.1f}% "
                                 f"du portefeuille > seuil 20%"
                                 if valeur_actuelle_totale and abs(perte_totale/valeur_actuelle_totale) > 0.20
                                 else None),
    }


def tous_les_stress_tests() -> list[dict]:
    """Lance tous les chocs prédéfinis en une passe."""
    return [stress_test_portefeuille(k) for k in CHOCS_PREDEFINIS]
