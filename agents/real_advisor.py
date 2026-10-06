"""
agents/real_advisor.py — Orchestrateur des conseils sur le portefeuille RÉEL.
Ne fait JAMAIS d'action automatique. Génère des conseils, attend la décision user.
Les règles sont dans agents/real_advisor_rules.py (v5.4.1).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.real_portfolio_db import lire_investissements, ajouter_conseil, lire_plan
from utils.real_price import calculate_position_pnl
from agents.asset_analyzer import analyser_actif_complet
from agents.decision_engine import decider
from agents.real_advisor_rules import regles_position, regle_signal_technique
from utils.registre_cycles import enregistrer_decisions

logger = get_logger(__name__)


def _enrichir(inv: dict) -> dict:
    """Ajoute prix actuel + P&L (calcul brut, affichage calibré) — v5.3.1."""
    try:
        pnl = calculate_position_pnl(inv)
    except Exception as e:
        logger.warning(f"calcul P&L {inv.get('asset')} : {e}")
        pnl = None
    if not pnl:
        return {**inv, "prix_actuel": None, "pnl_pct": None, "pnl_eur": None,
                "prix_calibre": False, "entry_price_display": inv["entry_price"]}
    return {
        **inv,
        "prix_actuel":          pnl["current_price_display"],
        "prix_actuel_raw":      pnl["current_price_raw"],
        "entry_price_display":  pnl["entry_price_display"],
        "pnl_pct":              pnl["pnl_percent"],
        "pnl_eur":              pnl["pnl_euros"],
        "current_value":        pnl["current_value"],
        "prix_calibre":         pnl["calibrated"],
        "prix_source":          pnl["source"],
    }


def _charger_plan(plan_id) -> dict | None:
    """Helper tolérant : retourne le plan ou None."""
    if not plan_id:
        return None
    try:
        return lire_plan(plan_id)
    except Exception:
        return None


def _enrichir_llm(conseils: list[dict], inv: dict, inv_e: dict, plan: dict) -> None:
    """Enrichit chaque conseil avec un wording LLM cohérent au plan (silencieux si KO)."""
    from utils.llm import ask_llm
    pnl_pct = inv_e["pnl_pct"]
    pnl_eur = inv_e["pnl_eur"]
    plan_name = plan.get("name", "")
    plan_type = plan.get("plan_type", "")
    plan_obj  = (plan.get("objective") or "")[:200]
    plan_vis  = (plan.get("vision") or "")[:200]
    plan_rea  = (plan.get("investment_reasons") or "")[:250]  # v5.4.3 : thèse
    plan_not  = (plan.get("personal_notes") or "")[:200]      # v5.4.3 : notes user
    for c in conseils:
        try:
            prompt = (f"Position : {inv['asset']} à {pnl_pct:+.1f}% ({pnl_eur:+.2f}€).\n"
                      f"Plan associé : {plan_name} ({plan_type})\n"
                      f"  Objectif : {plan_obj}\n"
                      f"  Vision   : {plan_vis}\n"
                      + (f"  Thèse    : {plan_rea}\n"  if plan_rea else "")
                      + (f"  Notes    : {plan_not}\n"  if plan_not else "")
                      + f"Conseil de base : {c['recommendation']} — {c['reasoning'][:200]}\n\n"
                      f"En 2 phrases max, conseil stratégique CONFORME au plan et à la thèse :")
            r = ask_llm(prompt,
                         system="Tu es un conseiller trading. Concis, factuel, respecte la stratégie du plan.",
                         mode="silent", max_tokens=200, appelant="conseiller_reel")
            if r.get("text"):
                c["reasoning"] = r["text"]
        except Exception:
            pass  # garder le conseil règle-base si LLM KO


def evaluer_position_reelle(inv: dict, passage=None) -> list[dict]:
    """Évalue une position réelle et génère des conseils si pertinent."""
    inv_e = _enrichir(inv)
    if inv_e["prix_actuel"] is None:
        return []
    plan = _charger_plan(inv.get("plan_id"))

    # Règles déterministes (toujours dispo, sans LLM)
    conseils = regles_position(inv, inv_e, plan)

    # Règle 4 : analyse technique (signal SELL fort)
    decision = analyses = None
    try:
        analyses = analyser_actif_complet(inv["asset"])
        # Phase 4 / Q2 : origine distincte pour garder l'ancien comportement du pipeline
        # (appel à chaque passage, sans cache ni mode Prudent)
        decision = decider(inv["asset"], analyses, origine="conseiller")
        c4 = regle_signal_technique(inv, decision, plan)
        if c4:
            conseils.append(c4)
    except Exception as e:
        logger.warning(f"Analyse {inv['asset']} pour conseil : {e}")

    # Enrichissement LLM optionnel
    if conseils and plan:
        _enrichir_llm(conseils, inv, inv_e, plan)
    if decision is not None:  # registre (Phase 4, R2) : décision du conseiller et conseils produits
        enregistrer_decisions(passage, [{"ticker": inv["asset"], "decision": decision, "analyses": analyses, "suite": {
            "resultat": "conseils", "investissement_id": inv.get("id"),
            "conseils": [{"type": c.get("advice_type"), "reco": c.get("recommendation"),
                          "urgence": c.get("urgency")} for c in conseils][:5]}}], None, "position_reelle", "conseiller")
    return conseils


def evaluer_tout_le_portefeuille(passage=None) -> int:
    """Boucle sur toutes les positions ouvertes, génère et enregistre les conseils.
    Retourne le nb de conseils créés."""
    invs = lire_investissements(filtre_status="OPEN")
    if not invs:
        return 0
    nb = 0
    for inv in invs:
        for conseil in evaluer_position_reelle(inv, passage):
            ajouter_conseil(inv["id"], conseil["advice_type"], conseil["recommendation"],
                            conseil["reasoning"], conseil["urgency"])
            nb += 1
            logger.info(f"  💡 Conseil {inv['asset']} : {conseil['recommendation']}")
    return nb
