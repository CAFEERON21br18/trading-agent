"""
utils/real_vue.py — Vues du portefeuille réel pour le dashboard (D1, 14/10/2026).

Ajoutent la devise des positions aux résumés de utils/real_portfolio_db.py sans
modifier ce module : resume_portefeuille() alimente aussi le prompt du chat, gelé
pendant le suivi de la consigne v2 (TODO §33). Les montants des positions restent
dans leur devise (utils/real_devise.py). Là où ils rencontrent des euros
(disponible, % investi, progression d'un plan), ils sont convertis avec le taux
affiché à côté (utils/real_conversion.py) ; sans taux : None, « non disponible ».
Une position ouverte sans prix n'est jamais comptée pour 0 (TODO §35).
"""

from utils.real_conversion import investi_en_eur, prix_par_actif, progression_plan_eur, sans_prix, texte_taux
from utils.real_devise import devise_commune, symbole
from utils.real_portfolio_db import get_budget_capital, lire_investissements, resume_portefeuille
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
    """Mêmes clés et même calcul que get_real_budget_summary() (real_portfolio_db.py),
    un prix par actif, plus :
    - actifs_sans_prix : si une position ouverte n'a pas de prix, current_value,
      unrealized_pnl et unrealized_pnl_percent valent None (TODO §35) ; investi et
      disponible ne dépendent pas du prix ;
    - available et invested_percent recalculés avec l'investi converti en € (le
      capital est en €) ; taux indisponible → None ;
    - la devise des positions, dans laquelle restent investi, valeur et plus-value."""
    positions = lire_investissements(filtre_status="OPEN")
    invested = sum(p["invested_amount"] for p in positions)
    by_holding = {"actif": 0.0, "passif": 0.0, "moyen": 0.0}
    by_instrument = {"normal": 0.0, "cfd": 0.0, "crypto": 0.0}
    for p in positions:
        h, i = p.get("holding_type", "moyen"), p.get("instrument_type", "normal")
        by_holding[h] = by_holding.get(h, 0) + p["invested_amount"]
        by_instrument[i] = by_instrument.get(i, 0) + p["invested_amount"]
    prix = prix_par_actif(positions)
    manquants = sans_prix(prix)
    valeur = pnl = pnl_pct = None
    if not manquants:
        valeur = 0.0
        for p in positions:
            valeur += p["quantity"] * prix[p["asset"]]
        pnl = valeur - invested if invested else 0.0
        pnl_pct = round(pnl / invested * 100, 1) if invested else 0
    investi_eur, taux = investi_en_eur(positions)
    capital, connu = get_budget_capital(), investi_eur is not None
    return {"total_capital": capital, "invested": invested, "current_value": valeur,
            "unrealized_pnl": pnl, "unrealized_pnl_percent": pnl_pct, "by_holding": by_holding,
            "by_instrument": by_instrument, "positions_count": len(positions),
            "actifs_sans_prix": manquants, **_devise(positions),
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
