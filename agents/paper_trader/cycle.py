"""
agents/paper_trader/cycle.py — Cycle complet du Paper Trading Engine
1. Monitor des positions ouvertes (SL/TP)
2. Ouverture des nouvelles positions selon les décisions du Decision Engine
3. Snapshot quotidien du portefeuille
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.portfolio_db import enregistrer_snapshot, lire_dernier_snapshot, initialiser_paper_db
from agents.paper_trader.portfolio import etat_portefeuille
from agents.paper_trader.executor import ouvrir_position_depuis_decision
from agents.paper_trader.monitor import monitorer_positions
from agents.paper_trader.rules import peut_ouvrir
from agents.budget_manager.manager import creer_demande, traiter_demandes
from agents.analysts.risk_manager.manager import valider_signal

logger = get_logger(__name__)


def initialiser() -> None:
    """À appeler au démarrage de la routine."""
    initialiser_paper_db()


def _decision_to_demande(d: dict) -> dict:
    """Transforme une décision BUY/SELL en demande budgétaire pour le BM.
    v4.1 : applique le taille_factor (learning = 0.2, contradiction = 0.5)."""
    dec = d["decision"]
    perf = (d["analyses"].get("memory", {}) or {}).get("perf") or {}
    sig  = (d["analyses"].get("risque", {}) or {}).get("signal") or {}
    budget_base = float(sig.get("montant_investi") or 100.0)
    taille_factor = float(dec.get("taille_factor", 1.0))
    style = dec.get("style", "normal")
    raison_base = dec.get("reasoning", "")[:160]
    if style == "learning":
        raison_base += " [LEARNING]"
    return creer_demande(
        demandeur=f"decision_engine ({style})",
        ticker=dec["ticker"],
        direction="LONG" if dec["decision"] == "BUY" else "SHORT",
        confiance=dec["confidence"],
        raison=raison_base,
        budget_souhaite=round(budget_base * taille_factor, 2),
        winrate_historique=float(perf.get("winrate_pct", 50.0)),
        urgence="haute" if dec["confidence"] >= 9 else "moyenne",
    )


def executer_ouvertures(decisions: list[dict]) -> dict:
    """
    Pipeline v4 : décisions BUY/SELL → Budget Manager → Risk Manager → Paper Trader.
    Retourne {"ouvertes", "refusees", "bm_resume"}.
    """
    actifs = [d for d in decisions if d["decision"]["decision"] in ("BUY", "SELL")]
    if not actifs:
        return {"ouvertes": [], "refusees": [], "bm_resume": None}

    demandes = [_decision_to_demande(d) for d in actifs]
    bm_resume = traiter_demandes(demandes)

    # Index ticker → décision originale
    par_ticker = {d["decision"]["ticker"]: d for d in actifs}
    ouvertes, refusees = [], []
    etat = etat_portefeuille(prix_courants={})

    for a in bm_resume["allocations"]:
        ticker = a["demande"]["actif"]
        d = par_ticker.get(ticker)
        if d is None:
            continue
        dec = d["decision"]
        prix = d["analyses"]["technique"]["prix"]
        direction = "LONG" if dec["decision"] == "BUY" else "SHORT"

        # Re-valider le risque avec le budget alloué par le BM
        validation = valider_signal(ticker, direction, prix, budget_alloue=a["budget_alloue"])
        if not validation["valide"]:
            refusees.append({"ticker": ticker, "raisons": validation["rejets"]})
            continue

        d["analyses"]["risque"] = validation  # injecter le risque ré-évalué
        ok, refus = peut_ouvrir(dec, d["analyses"], etat)
        if not ok:
            refusees.append({"ticker": ticker, "raisons": refus})
            continue

        pos_id = ouvrir_position_depuis_decision(dec, d["analyses"])
        if pos_id:
            ouvertes.append({"ticker": ticker, "decision": dec["decision"],
                             "pos_id": pos_id, "budget": a["budget_alloue"]})
            etat["open_positions_count"] += 1
            etat["invested"] += validation["signal"]["montant_investi"]

    # Demandes en attente / rejetées par le BM
    for d_at in bm_resume.get("en_attente", []):
        refusees.append({"ticker": d_at.get("actif", "?"),
                         "raisons": [d_at.get("raison_refus", "BM en attente")]})

    return {"ouvertes": ouvertes, "refusees": refusees, "bm_resume": bm_resume}


def enregistrer_snapshot_quotidien(prix_courants: dict | None = None) -> dict:
    """Calcule et enregistre le snapshot du jour."""
    etat = etat_portefeuille(prix_courants=prix_courants)
    dernier = lire_dernier_snapshot()
    capital_initial = dernier["total_value"] if dernier else etat["capital_total"]
    cumulative = ((etat["total_value"] / etat["capital_total"]) - 1) * 100

    snap = {
        "date":                      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "cash":                      etat["cash"],
        "invested":                  etat["invested"],
        "unrealized_pnl":            etat["unrealized_pnl"],
        "total_value":               etat["total_value"],
        "daily_return_percent":      etat["daily_return_percent"],
        "cumulative_return_percent": cumulative,
        "open_positions_count":      etat["open_positions_count"],
    }
    enregistrer_snapshot(snap)
    logger.info(f"Snapshot {snap['date']} : valeur {snap['total_value']:.2f}€, "
                f"P&L {snap['unrealized_pnl']:+.2f}€, {snap['open_positions_count']} pos")
    return snap


def formater_section_portefeuille(etat: dict, monitor_resume: dict, cycle_resume: dict) -> str:
    """Section markdown pour le rapport quotidien."""
    lignes = [
        "## 💼 Portefeuille Paper Trading",
        "",
        f"- **Capital total** : {etat['capital_total']:.2f}€  |  **Total value** : {etat['total_value']:.2f}€",
        f"- **Cash** : {etat['cash']:.2f}€  |  **Investi** : {etat['invested']:.2f}€  |  "
        f"**P&L non-réalisé** : {etat['unrealized_pnl']:+.2f}€",
        f"- **Positions ouvertes** : {etat['open_positions_count']}/{etat['max_positions']}",
    ]
    if etat["mode_defensif"]:
        lignes.append(f"- ⚠️ **Mode défensif activé** (risque {etat['risque_par_trade_pct']:.0f}%, "
                      f"seuil confiance {etat['seuil_confiance']}/10)")

    # Monitor
    if monitor_resume["verifiees"] > 0:
        lignes.append("")
        lignes.append(f"**Monitor SL/TP** : {monitor_resume['verifiees']} surveillée(s) — "
                      f"{monitor_resume['fermees_tp']} TP, {monitor_resume['fermees_sl']} SL")

    # Cycle
    lignes.append("")
    if cycle_resume["ouvertes"]:
        lignes.append(f"**Nouvelles positions** ({len(cycle_resume['ouvertes'])}) :")
        for o in cycle_resume["ouvertes"]:
            lignes.append(f"  - 🚀 {o['ticker']} {o['decision']} (#{o['pos_id']})")
    if cycle_resume["refusees"]:
        lignes.append(f"**Ouvertures refusées** ({len(cycle_resume['refusees'])}) :")
        for r in cycle_resume["refusees"]:
            lignes.append(f"  - ⏸️ {r['ticker']} {r['decision']} ({r['confidence']}/10) — {r['raisons'][0]}")
    if not cycle_resume["ouvertes"] and not cycle_resume["refusees"]:
        lignes.append("**Pas de candidats BUY/SELL aujourd'hui.**")

    # Positions ouvertes (détail)
    if etat["open_positions"]:
        lignes.append("")
        lignes.append("**Positions ouvertes** :")
        lignes.append("| Actif | Dir | Entrée | Actuel | P&L | SL | TP1 |")
        lignes.append("|-------|-----|--------|--------|-----|-----|-----|")
        for p in etat["open_positions"]:
            pnl = p.get("unrealized_pnl_pct")
            pnl_str = f"{pnl:+.2f}%" if pnl is not None else "N/A"
            actuel = p.get("prix_actuel")
            actuel_str = f"{actuel:.4f}" if actuel else "N/A"
            lignes.append(f"| {p['ticker']} | {p['direction']} | {p['entry_price']:.4f} | "
                          f"{actuel_str} | {pnl_str} | {p['stop_loss']:.4f} | {p['target_1']:.4f} |")

    return "\n".join(lignes)
