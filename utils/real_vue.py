"""
utils/real_vue.py — Vues du portefeuille réel pour le dashboard (D1, 14/10/2026).

Ajoutent la devise des positions aux résumés de utils/real_portfolio_db.py sans
modifier ce module : resume_portefeuille() alimente aussi le prompt du chat, gelé
pendant le suivi de la consigne v2 (TODO §33). Les montants des positions restent
dans leur devise (utils/real_devise.py). Les chiffres qui mélangent ces montants
et des euros (disponible, % investi, progression d'un plan) sont non convertis.
"""

from utils.real_devise import devise_commune, symbole
from utils.real_portfolio_db import (get_real_budget_summary, lire_investissements,
                                     positions_du_plan, progression_plan, resume_portefeuille)
from utils.real_price import calibrate_to_revolut

MIXTE = " (devises mélangées)"


def _devise(positions: list[dict]) -> dict:
    """{devise_positions, symbole_positions} ; symbole_positions = MIXTE si plusieurs devises."""
    d = devise_commune(positions)
    return {"devise_positions": d, "symbole_positions": symbole(d) if d else MIXTE}


def resume_portefeuille_vue() -> dict:
    """resume_portefeuille() + devise des positions (ouvertes et closes)."""
    return {**resume_portefeuille(), **_devise(lire_investissements())}


def budget_reel_vue() -> dict:
    """get_real_budget_summary() + devise des positions ouvertes.
    available et invested_percent mêlent le capital (€) et l'investi (devise des
    positions) : non convertis."""
    return {**get_real_budget_summary(), **_devise(lire_investissements(filtre_status="OPEN"))}


def progression_plan_vue(plan_id: int) -> dict:
    """progression_plan() + devise des positions du plan. progression_pct et
    avancement_objectif divisent un P&L (devise des positions) par un budget en
    euros : non convertis."""
    prog = progression_plan(plan_id)
    if "error" in prog:
        return prog
    return {**prog, **_devise(positions_du_plan(plan_id))}


def calibrer_vue(ticker: str, revolut_price: float, devise: str | None = None) -> dict:
    """calibrate_to_revolut avec l'écart libellé dans la devise de cotation."""
    return calibrate_to_revolut(ticker, revolut_price, symbole(devise))
