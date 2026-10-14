"""
utils/real_conversion.py — Conversion en euros aux points de rencontre du portefeuille
réel (D1, 14/10/2026), hors chat : investi face au capital, P&L d'un plan face à son
budget. Le capital (real_budget) et les budgets des plans sont en euros ; les montants
d'une position restent dans sa devise et ne sont jamais convertis pour eux-mêmes.

Taux indisponible (utils/fx.py) → None, affiché « non disponible » : jamais un
résultat calculé au taux 1. Le prompt du chat n'utilise aucune de ces fonctions.
"""

from utils.fx import en_eur, libelle_taux
from utils.real_devise import devise_commune, devise_de
from utils.real_portfolio_db import lire_plan, positions_du_plan, progression_plan


def investi_en_eur(positions: list[dict]) -> tuple[float | None, dict]:
    """(somme des montants investis convertie en €, {devise: taux utilisé}) ;
    (None, taux déjà lus) si un taux manque."""
    par_devise: dict = {}
    for p in positions:
        d = devise_de(p)
        par_devise[d] = par_devise.get(d, 0.0) + float(p.get("invested_amount") or 0)
    total, taux = 0.0, {}
    for d, montant in sorted(par_devise.items()):
        valeur, info = en_eur(montant, d)
        if valeur is None:
            return None, taux
        total += valeur
        taux[d] = info
    return total, taux


def texte_taux(taux: dict | None, manque: bool = False) -> str:
    """Ligne affichée à côté d'un résultat converti."""
    if manque:
        return "conversion en € non disponible (taux de change introuvable)"
    convertis = [i for i in (taux or {}).values() if i.get("horodatage")]  # l'euro n'a pas de taux
    if not convertis:
        return "aucune conversion nécessaire"
    return "converti en € au taux " + " ; ".join(libelle_taux(i) for i in convertis)


def progression_plan_eur(plan_id: int) -> dict:
    """progression_plan() avec le P&L converti en € AVANT la division par le budget (€).
    progression_pct et avancement_objectif valent None si le taux manque ou si les
    positions du plan ont plusieurs devises. Montants des positions inchangés.
    Sans budget en €, progression_plan divise par l'investi : rapport homogène, inchangé."""
    prog = progression_plan(plan_id)
    if "error" in prog:
        return prog
    positions = positions_du_plan(plan_id)
    devise = devise_commune(positions)
    budget = (lire_plan(plan_id) or {}).get("allocated_budget")
    if not budget:
        return {**prog, "devise_positions": devise, "pnl_total_eur": None, "taux_change": None,
                "taux_libelle": "sans conversion : budget = montant investi"}
    pnl_eur, info = en_eur(prog["pnl_total"], devise) if devise else (None, None)
    if pnl_eur is None:
        return {**prog, "devise_positions": devise, "pnl_total_eur": None, "progression_pct": None,
                "avancement_objectif": None, "taux_change": None,
                "taux_libelle": texte_taux(None, manque=True) if devise
                else "conversion en € non disponible (positions en plusieurs devises)"}
    progression = pnl_eur / budget * 100
    cible = prog.get("target_pct") or 0
    avancement = progression / cible * 100 if cible > 0 else None
    return {**prog, "devise_positions": devise, "pnl_total_eur": round(pnl_eur, 2),
            "progression_pct": round(progression, 2),
            "avancement_objectif": round(avancement, 1) if avancement is not None else None,
            "taux_change": info, "taux_libelle": texte_taux({devise: info})}
