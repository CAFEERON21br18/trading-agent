"""
agents/real_advisor.py — Conseil pour le portefeuille RÉEL (v5.0)
Ne fait JAMAIS d'action automatique. Génère des conseils, attend la décision user.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.real_portfolio_db import lire_investissements, ajouter_conseil
from utils.real_price import get_adjusted_price
from agents.asset_analyzer import analyser_actif_complet
from agents.decision_engine import decider

logger = get_logger(__name__)


def _enrichir(inv: dict) -> dict:
    """Ajoute prix actuel calibré (Revolut) + P&L latent au dict d'investissement réel."""
    try:
        info = get_adjusted_price(inv["asset"])
        prix = info.get("price")
    except Exception:
        prix = None
        info = {}
    if prix is None:
        return {**inv, "prix_actuel": None, "pnl_pct": None, "pnl_eur": None,
                "prix_calibre": False}
    if inv["direction"] == "LONG":
        pnl_eur = (prix - inv["entry_price"]) * inv["quantity"]
    else:
        pnl_eur = (inv["entry_price"] - prix) * inv["quantity"]
    pnl_pct = (pnl_eur / inv["invested_amount"] * 100) if inv["invested_amount"] else 0
    return {**inv, "prix_actuel": prix, "pnl_pct": pnl_pct, "pnl_eur": pnl_eur,
            "prix_calibre": bool(info.get("calibrated")),
            "prix_source":  info.get("source")}


def evaluer_position_reelle(inv: dict) -> list[dict]:
    """
    Évalue une position réelle et génère des conseils si pertinent.
    Retourne liste de {advice_type, recommendation, reasoning, urgency}.
    """
    conseils = []
    inv_e = _enrichir(inv)
    prix = inv_e["prix_actuel"]
    if prix is None:
        return conseils

    pnl_pct = inv_e["pnl_pct"]
    target  = inv["target_price"]
    sl      = inv["stop_loss_mental"]

    # 1. Cible atteinte
    if target and inv["direction"] == "LONG" and prix >= target * 0.97:
        conseils.append({
            "advice_type": "ALERTE",
            "recommendation": "prendre profit partiel",
            "reasoning": f"{inv['asset']} approche ta cible {target:.2f} (actuel {prix:.2f}, +{pnl_pct:.1f}%). "
                         "Envisage de prendre 50% de profit, laisser courir le reste.",
            "urgency": "haute",
        })

    # 2. Stop mental violé
    if sl and inv["direction"] == "LONG" and prix <= sl:
        conseils.append({
            "advice_type": "ALERTE",
            "recommendation": "vendre / couper",
            "reasoning": f"{inv['asset']} a passé ton stop mental {sl:.2f} (actuel {prix:.2f}, {pnl_pct:.1f}%). "
                         "Ta thèse est-elle invalidée ? Si oui, couper proprement.",
            "urgency": "haute",
        })

    # 3. Position trop chargée en perte
    if pnl_pct < -15:
        conseils.append({
            "advice_type": "CONSEIL",
            "recommendation": "réévaluer la thèse",
            "reasoning": f"{inv['asset']} en perte de {pnl_pct:.1f}%. "
                         f"Thèse initiale : '{inv.get('investment_thesis', 'non documentée')}'. "
                         "Reste-t-elle valable ? Sinon, coupe et redéploie.",
            "urgency": "moyenne",
        })

    # 4. Analyse technique défavorable
    try:
        analyses = analyser_actif_complet(inv["asset"])
        decision = decider(inv["asset"], analyses)
        if inv["direction"] == "LONG" and decision["decision"] == "SELL" and decision["confidence"] >= 7:
            conseils.append({
                "advice_type": "CONSEIL",
                "recommendation": "envisager fermeture",
                "reasoning": f"L'agent détecte un signal SELL fort sur {inv['asset']} "
                             f"(conf {decision['confidence']}/10) : {decision['reasoning'][:200]}",
                "urgency": "moyenne",
            })
    except Exception as e:
        logger.warning(f"Analyse {inv['asset']} pour conseil : {e}")

    return conseils


def evaluer_tout_le_portefeuille() -> int:
    """Boucle sur toutes les positions ouvertes, génère et enregistre les conseils.
    Retourne le nb de conseils créés."""
    invs = lire_investissements(filtre_status="OPEN")
    if not invs:
        return 0
    nb = 0
    for inv in invs:
        for conseil in evaluer_position_reelle(inv):
            ajouter_conseil(inv["id"], conseil["advice_type"], conseil["recommendation"],
                            conseil["reasoning"], conseil["urgency"])
            nb += 1
            logger.info(f"  💡 Conseil {inv['asset']} : {conseil['recommendation']}")
    return nb
