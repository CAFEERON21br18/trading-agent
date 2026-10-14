"""
utils/real_vue.py — Vues du portefeuille réel pour le dashboard (D1, 14/10/2026).

Ajoutent la devise des positions aux résumés de utils/real_portfolio_db.py sans
modifier ce module : resume_portefeuille() alimente aussi le prompt du chat, gelé
pendant le suivi de la consigne v2 (TODO §33). Les montants des positions restent
dans leur devise (utils/real_devise.py). Là où ils rencontrent des euros
(disponible, % investi, progression d'un plan), ils sont convertis avec le taux
affiché à côté (utils/real_conversion.py) ; sans taux : None, « non disponible ».
"""

from utils.real_conversion import investi_en_eur, progression_plan_eur, texte_taux
from utils.real_devise import devise_commune, symbole
from utils.real_portfolio_db import get_real_budget_summary, lire_investissements, resume_portefeuille
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
    """get_real_budget_summary() + devise des positions ouvertes. available et
    invested_percent sont recalculés avec l'investi converti en € (le capital est en
    €) ; taux indisponible → None. Investi, valeur et plus-value restent dans la
    devise des positions."""
    b = get_real_budget_summary()
    positions = lire_investissements(filtre_status="OPEN")
    investi_eur, taux = investi_en_eur(positions)
    capital, connu = b["total_capital"], investi_eur is not None
    return {**b, **_devise(positions),
            "invested_eur": round(investi_eur, 2) if connu else None,
            "available": round(capital - investi_eur, 2) if connu else None,
            "invested_percent": (round(investi_eur / capital * 100, 1) if capital else 0) if connu else None,
            "taux_change": taux if connu else None,
            "taux_libelle": texte_taux(taux, manque=not connu)}


def progression_plan_vue(plan_id: int) -> dict:
    """progression_plan_eur() (P&L converti en € avant la division par le budget)
    + symbole des positions du plan."""
    prog = progression_plan_eur(plan_id)
    if "error" in prog:
        return prog
    d = prog["devise_positions"]
    return {**prog, "symbole_positions": symbole(d) if d else MIXTE}


def calibrer_vue(ticker: str, revolut_price: float, devise: str | None = None) -> dict:
    """calibrate_to_revolut avec l'écart libellé dans la devise de cotation."""
    return calibrate_to_revolut(ticker, revolut_price, symbole(devise))
