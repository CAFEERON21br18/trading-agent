"""
agents/paper_trader/rules.py — Règles d'entrée (filtre final avant exécution paper)
Vérifie : confiance, convergence, capacité portefeuille, doublon actif, mode défensif.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import lire_position_ouverte_actif

logger = get_logger(__name__)

CONVERGENCES_REQUISES = 0   # v4.1 : convergences NON OBLIGATOIRES (avant 1)


def peut_ouvrir(decision: dict, analyses: dict, etat_porte: dict) -> tuple[bool, list[str]]:
    """
    Décide si on peut ouvrir une position paper à partir de la décision du Decision Engine.
    v4.1 : trades d'apprentissage acceptés avec confiance 4+, convergences non requises.
    Retourne (ok, raisons_refus).
    """
    refus = []
    ticker = decision["ticker"]
    style = decision.get("style", "normal")

    # 1. Décision finale doit être BUY ou SELL
    if decision["decision"] not in ("BUY", "SELL"):
        refus.append(f"Décision = {decision['decision']} (ni BUY ni SELL)")

    # 2. Confiance ≥ seuil (v4.1 : 4 minimum pour learning, sinon seuil mode BM)
    seuil = etat_porte.get("seuil_confiance", config.ALERT_CONFIDENCE_THRESHOLD)
    seuil_min_absolu = 4 if style == "learning" else seuil
    if decision["confidence"] < seuil_min_absolu:
        refus.append(f"Confiance {decision['confidence']}/10 < seuil {seuil_min_absolu}/10 ({style})")

    # 3. Convergences (v4.1 : non obligatoires — même 0 convergence acceptée)
    if CONVERGENCES_REQUISES > 0 and len(decision.get("convergences", [])) < CONVERGENCES_REQUISES:
        refus.append(f"Pas assez de convergences ({len(decision.get('convergences', []))} < {CONVERGENCES_REQUISES})")

    # 4. Risk Manager doit valider
    risk = analyses.get("risque", {})
    if not risk.get("valide") or not risk.get("signal"):
        rejets = risk.get("rejets", [])
        refus.append(f"Risk Manager : {' | '.join(rejets) if rejets else 'invalide'}")

    # 5. Max positions ouvertes
    if etat_porte.get("open_positions_count", 0) >= etat_porte.get("max_positions", 5):
        refus.append(f"Max positions atteint ({etat_porte['open_positions_count']}/{etat_porte['max_positions']})")

    # 6. Pas de position déjà ouverte sur cet actif
    if lire_position_ouverte_actif(ticker):
        refus.append(f"Position déjà ouverte sur {ticker}")

    # 7. Cash insuffisant
    cash = etat_porte.get("cash", 0)
    invested_cap = etat_porte.get("capital_investissable", 0)
    if invested_cap - etat_porte.get("invested", 0) <= 0:
        refus.append(f"Capital investissable épuisé (déjà {etat_porte.get('invested', 0):.0f}€ investis sur {invested_cap:.0f}€)")

    return len(refus) == 0, refus
