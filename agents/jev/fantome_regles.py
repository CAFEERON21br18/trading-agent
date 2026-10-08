"""
agents/jev/fantome_regles.py — Règles du portefeuille fantôme Jev (REGISTRE_CRITERES §8.2).

Fonctions pures, sans base ni réseau : motifs de refus, taille plafonnée comme
le paper mais sur l'état du fantôme, sortie à J+5, P&L net de coûts.
Horizon, seuil p(acheter) et coûts viennent de scripts/jev_bilan_calc.py :
ce sont ceux du §7.1, sans copie.
"""

import json

from agents.jev.questions import FACTEURS_CONVICTION
from agents.budget_manager.strategy import PARAMETRES as MODES_BM
from agents.budget_manager.arbitrator import MONTANT_MIN_VIABLE
from scripts.jev_bilan_calc import HORIZON, SEUIL_ACHETER, cout  # noqa: F401 (SEUIL_ACHETER réexporté)


def direction_signal(state: str | None) -> str | None:
    """Direction du signal du Risk Manager dans le state stocké (LONG / SHORT) ; None si absente."""
    try:
        return ((json.loads(state or "{}").get("risque") or {}).get("signal") or {}).get("direction")
    except (ValueError, AttributeError):
        return None


def motif_avant_taille(obs: dict, tickers_fantomes: set) -> str | None:
    """Premier motif de refus du §8.2 qui ne dépend pas de la taille ; None si l'achat reste possible."""
    if obs.get("position_ouverte"):
        return "position_paper_ouverte"      # condition 2 : position paper figée dans l'observation (§7.1)
    if obs["ticker"] in tickers_fantomes:
        return "position_fantome_ouverte"    # condition 3
    if not obs.get("conviction_niveau"):     # niveau 0 (ou absent) : facteur de taille nul
        return "conviction_nulle"
    if not obs.get("prix"):
        return "sans_prix"
    if obs.get("montant_risque") is None:
        return "sans_montant_risque"         # technique neutre : Risk Manager non appelé
    direction = direction_signal(obs.get("state"))
    if direction == "SHORT":
        return "montant_vente_a_decouvert"   # montant calculé pour une vente à découvert
    if direction != "LONG":
        return "sans_montant_risque"         # direction illisible : pas de montant acheteur connu
    if obs.get("mode_bm") not in MODES_BM:
        return "sans_mode_bm"
    return None


def taille(obs: dict, investi: float, nb_ouvertes: int, max_positions: int,
           capital: float) -> tuple[dict | None, str | None, dict]:
    """(entrée ou None, motif ou None, détails). Plafonds du paper sur l'état du fantôme :
    max par trade du mode × cash libre ; cash libre = capital investissable du mode − investi
    fantôme ; nombre de positions ; minimum viable du Budget Manager (15 €)."""
    mode = MODES_BM[obs["mode_bm"]]
    facteur = FACTEURS_CONVICTION[obs["conviction_niveau"]]
    cash_libre = max(0.0, capital * mode["capital_investissable_pct"] / 100 - investi)
    max_trade = mode["max_conviction_par_trade"] / 100 * cash_libre
    brut = facteur * float(obs["montant_risque"])
    montant = round(min(brut, max_trade, cash_libre), 2)
    details = {"facteur": facteur, "montant_brut": round(brut, 2), "max_par_trade": round(max_trade, 2),
               "cash_libre": round(cash_libre, 2), "montant": montant, "positions_ouvertes": nb_ouvertes}
    if nb_ouvertes >= max_positions:
        return None, "max_positions", details
    if montant < MONTANT_MIN_VIABLE:
        return None, "sous_minimum", details
    return {"montant": montant, "quantite": montant / float(obs["prix"]), "facteur": facteur}, None, details


def barre_sortie(barres: list, jour_cycle: str) -> tuple[str, float] | None:
    """(date, clôture) de la 5e barre datée du jour d'entrée ou après (J+5 du §7.1), si elle
    est close au cycle de jour_cycle, c'est-à-dire datée d'avant ce jour ; None sinon.
    barres : les HORIZON premières barres (date, clôture), triées par date."""
    if len(barres) < HORIZON:
        return None
    date_barre, cloture = barres[HORIZON - 1]
    return (date_barre, float(cloture)) if date_barre < jour_cycle else None


def resultat(position: dict, prix_sortie: float) -> dict:
    """P&L de sortie, coûts aller-retour du §7.1 déduits sur le montant investi.
    pnl_pct (fraction) = rendement du §7.1 : sortie / entrée − 1 − coût."""
    cout_pct = cout(position["ticker"])
    brut = position["quantite"] * (prix_sortie - position["prix_entree"])
    cout_euros = cout_pct * position["montant_investi"]
    net = brut - cout_euros
    return {"cout_pct": cout_pct, "cout_euros": cout_euros, "pnl_brut": brut, "pnl_net": net,
            "pnl_pct": net / position["montant_investi"]}
