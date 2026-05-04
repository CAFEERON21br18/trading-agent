"""
agents/budget_manager/manager.py — Interface principale du Budget Manager
Banquier de l'agent : alloue le capital entre toutes les opportunités.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger
from utils.portfolio_db import lire_positions_ouvertes
from agents.budget_manager.strategy import (
    detecter_mode, parametres_mode, capital_investissable, diagnostic,
)
from agents.budget_manager.arbitrator import arbitrer

logger = get_logger(__name__)


def creer_demande(demandeur: str, ticker: str, direction: str, confiance: int,
                  raison: str, budget_souhaite: float,
                  winrate_historique: float = 50.0,
                  urgence: str = "moyenne", duree: str = "swing") -> dict:
    """Construit une demande budgétaire normalisée."""
    return {
        "demandeur":           demandeur,
        "actif":               ticker,
        "direction":           direction,
        "confiance":           confiance,
        "raison":              raison,
        "budget_souhaité":     round(budget_souhaite, 2),
        "winrate_historique":  winrate_historique,
        "urgence":             urgence,
        "durée_estimée":       duree,
        "timestamp":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _cash_disponible_actuel(mode: str) -> float:
    """Cash investissable libre = capital_investissable(mode) - somme(positions ouvertes)."""
    cap_inv = capital_investissable(mode)
    deja_investi = sum(p["invested_amount"] for p in lire_positions_ouvertes())
    return max(0.0, cap_inv - deja_investi)


def traiter_demandes(demandes: list[dict], conviction_force: bool = False) -> dict:
    """
    Point d'entrée principal : reçoit une liste de demandes, retourne les allocations.
    """
    mode = detecter_mode(conviction_force=conviction_force)
    params = parametres_mode(mode)
    cash_dispo = _cash_disponible_actuel(mode)

    logger.info(f"Budget Manager — mode {mode}, cash dispo {cash_dispo:.2f}€, "
                f"{len(demandes)} demande(s)")

    if cash_dispo <= 0:
        return {
            "mode":         mode,
            "cash_dispo":   0.0,
            "allocations":  [],
            "total_alloue": 0.0,
            "en_attente":   demandes,
            "message":      "Capital investissable épuisé — aucune nouvelle position",
        }

    res = arbitrer(demandes, cash_dispo, params)
    res["mode"] = mode
    res["cash_dispo"] = cash_dispo
    return res


def tableau_de_bord() -> str:
    """Génère le tableau de bord textuel du Budget Manager."""
    diag = diagnostic()
    mode = diag["mode"]
    cap_total = config.CAPITAL
    cap_inv = capital_investissable(mode)
    reserve = cap_total - cap_inv
    positions = lire_positions_ouvertes()
    investi = sum(p["invested_amount"] for p in positions)
    cash_dispo = cap_inv - investi

    lignes = [
        "BUDGET MANAGER — ÉTAT DES FONDS",
        "─" * 50,
        f"Mode actuel             : {mode}",
        f"Capital total           : {cap_total:.2f}€",
        f"Réserve intouchable     : {reserve:.2f}€",
        f"Capital investissable   : {cap_inv:.2f}€",
        "─" * 50,
        f"Investi actuellement    : {investi:.2f}€ ({investi / cap_inv * 100:.1f}% si cap_inv > 0)" if cap_inv > 0 else f"Investi : {investi:.2f}€",
        f"Cash disponible         : {cash_dispo:.2f}€",
        "─" * 50,
        f"Trades wins consécutifs : {diag['wins_consecutifs']}",
        f"Trades pertes consécutifs : {diag['pertes_consecutives']}",
        f"Drawdown récent (10 last) : {diag['drawdown_pct']}%",
        "─" * 50,
        "Positions ouvertes :",
    ]
    if not positions:
        lignes.append("  (aucune)")
    else:
        for p in positions:
            pnl_str = f" — P&L: {p.get('unrealized_pnl_euros', 0):+.2f}€" if p.get("unrealized_pnl_euros") is not None else ""
            lignes.append(
                f"  {p['ticker']:<8} : {p['invested_amount']:>7.2f}€ "
                f"({p['invested_amount'] / cap_inv * 100:.1f}%){pnl_str}"
            )
    return "\n".join(lignes)


def formater_section_budget(res: dict) -> str:
    """Génère un bloc markdown pour le rapport quotidien."""
    lignes = [
        f"## 💰 Budget Manager — mode **{res['mode']}**",
        "",
        f"- Cash disponible : **{res['cash_dispo']:.2f}€**",
        f"- Total alloué : **{res['total_alloue']:.2f}€**",
        f"- Cash restant après allocation : {res.get('cash_restant', 0):.2f}€",
    ]
    if res["allocations"]:
        lignes.append("\n**Allocations** :")
        for a in res["allocations"]:
            d = a["demande"]
            lignes.append(f"- 🟢 **{d['actif']}** {d['direction']} — alloué **{a['budget_alloue']:.2f}€** "
                          f"(demandé {a['budget_demande']:.2f}€) — {a['raison_allocation']}")
    if res["en_attente"]:
        lignes.append("\n**En attente / refusées** :")
        for d in res["en_attente"]:
            lignes.append(f"- ⏸️ {d['actif']} {d.get('direction', '')} — {d.get('raison_refus', 'pas de cash')}")
    return "\n".join(lignes)
