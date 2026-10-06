"""
agents/paper_trader/executor.py — Exécuteur de trades virtuels
Ouvre / ferme les positions paper et envoie un email de notification.
AUCUNE connexion à un broker réel — tout est simulé.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import (
    creer_position, fermer_position as db_fermer_position,
    lire_position_ouverte_actif,
)
from alerts.channels.email_channel import envoyer_email

logger = get_logger(__name__)


def _format_prix(p: float) -> str:
    return f"{p:,.4f}".rstrip("0").rstrip(".")


def _email_ouverture(p: dict) -> None:
    """Notification email — nouvelle position ouverte (paper)."""
    pct_sl = (p["stop_loss"] / p["entry_price"] - 1) * 100
    pct_tp1 = (p["target_1"] / p["entry_price"] - 1) * 100
    sujet = f"🚀 [PAPER] Nouvelle position {p['direction']} {p['ticker']} ({p['confidence']}/10)"
    corps = (
        f"NOUVELLE POSITION PAPIER OUVERTE\n\n"
        f"Actif            : {p['ticker']}\n"
        f"Direction        : {p['direction']}\n"
        f"Prix d'entrée    : {_format_prix(p['entry_price'])}\n"
        f"Quantité         : {p['quantity']:.6f} unités\n"
        f"Montant investi  : {p['invested_amount']:.2f}€\n"
        f"Stop-loss        : {_format_prix(p['stop_loss'])} ({pct_sl:+.2f}%)\n"
        f"Target 1         : {_format_prix(p['target_1'])} ({pct_tp1:+.2f}%)\n"
        f"Target 2         : {_format_prix(p['target_2']) if p.get('target_2') else 'N/A'}\n"
        f"Confiance        : {p['confidence']}/10\n\n"
        f"Raison : {p.get('entry_reason', '')}\n\n"
        f"⚠️ Paper trading — aucun ordre réel exécuté."
    )
    envoyer_email(sujet, corps)


def _email_fermeture(res: dict, raison: str, status: str) -> None:
    """Notification email — position fermée (gain ou perte)."""
    pnl_e = res["pnl_euros"]
    pnl_p = res["pnl_percent"]
    if pnl_e >= 0:
        emoji, qualif = "🟢", "GAIN"
    else:
        emoji, qualif = "🔴", "PERTE"
    sujet = f"{emoji} [PAPER] Position fermée {res['ticker']} — {pnl_e:+.2f}€ ({pnl_p:+.2f}%)"
    corps = (
        f"POSITION PAPIER FERMÉE — {qualif}\n\n"
        f"Actif         : {res['ticker']}\n"
        f"Direction     : {res['direction']}\n"
        f"Prix d'entrée : {_format_prix(res['entry_price'])}\n"
        f"P&L           : {pnl_e:+.2f}€ ({pnl_p:+.2f}%)\n"
        f"Statut        : {status}\n"
        f"Raison sortie : {raison}\n\n"
        f"⚠️ Paper trading — aucun ordre réel exécuté."
    )
    envoyer_email(sujet, corps)


def ouvrir_position_depuis_decision(decision: dict, analyses: dict) -> int | None:
    """
    Crée une position en BDD à partir de la décision du Decision Engine.
    Vérifie qu'aucune position n'existe déjà sur le même actif.
    Retourne l'id créé ou None.
    """
    ticker = decision["ticker"]
    if lire_position_ouverte_actif(ticker):
        logger.info(f"Position déjà ouverte sur {ticker} — pas de doublon")
        return None

    risk = analyses.get("risque", {})
    if not (risk.get("valide") and risk.get("signal")):
        logger.warning(f"Risque non validé pour {ticker} — ouverture annulée")
        return None
    sig = risk["signal"]

    direction = "LONG" if decision["decision"] == "BUY" else "SHORT"
    style = decision.get("style", "normal")
    prefixe = "[LEARNING] " if style == "learning" else ""
    payload = {
        "ticker":          ticker,
        "asset_type":      _detecter_type(ticker),
        "direction":       direction,
        "entry_price":     sig["prix_entree"],
        "quantity":        sig["taille_unites"],
        "invested_amount": sig["montant_investi"],
        "stop_loss":       sig["stop_loss"],
        "target_1":        sig["target_1"],
        "target_2":        sig["target_2"],
        "confidence":      decision["confidence"],
        "entry_reason":    prefixe + decision.get("reasoning", ""),
        "signals_used":    f"DE [{style}] | conv:{len(decision.get('convergences', []))} | "
                           f"contra:{len(decision.get('contradictions', []))}"
                           # Phase 4 / Q2 : position ouverte en mode Prudent (pipeline en échec)
                           + (" | pipeline:fallback" if (decision.get("pipeline_raisonnement") or {}).get("fallback") else ""),
    }
    pos_id = creer_position(payload)
    logger.info(f"Position #{pos_id} ouverte (paper) : {direction} {ticker} {payload['quantity']:.6f}u "
                f"= {payload['invested_amount']:.2f}€")
    _email_ouverture(payload)
    return pos_id


def fermer_position(pos_id: int, exit_price: float, raison: str, status: str) -> dict | None:
    """Ferme une position et notifie. status ∈ {CLOSED_TP, CLOSED_SL, CLOSED_MANUAL, CLOSED_REVERSAL}."""
    res = db_fermer_position(pos_id, exit_price, raison, status)
    if res is None:
        logger.error(f"Position #{pos_id} introuvable pour fermeture")
        return None
    logger.info(f"Position #{pos_id} ({res['ticker']}) fermée [{status}] — P&L {res['pnl_euros']:+.2f}€")
    _email_fermeture(res, raison, status)
    return res


def _detecter_type(ticker: str) -> str:
    """Classification rapide pour reporting."""
    if ticker.endswith("-USD"):
        return "crypto"
    if ticker.endswith("=F"):
        return "cfd"
    if ticker in {"SPY", "QQQ", "VOO"}:
        return "etf"
    return "action"
