"""
agents/chat/_plan_budget.py — Plafond du budget d'un plan créé via le chat (Phase 4 / E4).

Le mode plan du chat ne crée que des plans RACINES (pas de parent_plan_id).
Plafond d'un nouveau plan :
    capital − investi − Σ restant des plans racines actifs
avec restant = max(0, budget du plan − investi sur les positions rattachées à
ce plan ou à ses sous-plans) : chaque position et chaque euro de budget ne sont
comptés qu'une fois (le budget d'un parent contient ceux de ses enfants).
Racine = plan actif sans parent actif (un sous-plan actif dont le parent est en
pause réserve toujours son budget). Actif = status 'active', seul critère lu
par le code (cf. plan_advisor). Calcul local, sans appel réseau.

Contient aussi formater_recap, déplacé tel quel depuis plan_builder.py pour que
celui-ci reste sous la limite de 200 lignes.
"""

from utils.real_portfolio_db import get_budget_capital, lire_investissements, lire_plans


def plafond_nouveau_plan() -> dict:
    """{plafond, capital, investi, reserve, plans} — montants en €, plans = racines réservantes."""
    capital = float(get_budget_capital() or 0)
    positions = lire_investissements(filtre_status="OPEN")
    investi = sum(float(p.get("invested_amount") or 0) for p in positions)
    plans = lire_plans()  # budgets en % déjà convertis en €
    actifs = {p["id"] for p in plans if p.get("status") == "active"}
    enfants: dict = {}
    for p in plans:
        enfants.setdefault(p.get("parent_plan_id"), []).append(p["id"])

    def sous_arbre(pid: int) -> set:
        vus, a_voir = set(), [pid]
        while a_voir:
            i = a_voir.pop()
            if i not in vus:
                vus.add(i)
                a_voir += enfants.get(i, [])
        return vus

    reserve, noms = 0.0, []
    for p in plans:
        if p["id"] not in actifs or p.get("parent_plan_id") in actifs:
            continue  # inactif, ou déjà compté via son parent actif
        ids = sous_arbre(p["id"])
        investi_arbre = sum(float(x.get("invested_amount") or 0) for x in positions
                            if x.get("plan_id") in ids)
        restant = max(0.0, float(p.get("allocated_budget") or 0) - investi_arbre)
        reserve += restant
        if restant > 0:
            noms.append(p.get("name") or f"#{p['id']}")
    return {"plafond": round(capital - investi - reserve, 2), "capital": capital,
            "investi": round(investi, 2), "reserve": round(reserve, 2), "plans": noms}


def _eur(v: float) -> str:
    """1787.37 → « 1 787,37 € »."""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _detail(f: dict) -> str:
    noms = f" ({', '.join(f['plans'][:3])}{'…' if len(f['plans']) > 3 else ''})" if f["plans"] else ""
    return (f"capital {_eur(f['capital'])} − investi {_eur(f['investi'])} − "
            f"budget restant des plans actifs {_eur(f['reserve'])}{noms}")


def resume_plafond() -> str:
    """Ligne d'accueil du mode plan."""
    try:
        f = plafond_nouveau_plan()
        return f"Budget disponible pour un nouveau plan : {_eur(f['plafond'])} ({_detail(f)})"
    except Exception:
        return "Budget disponible pour un nouveau plan : illisible pour l'instant"


def refus_budget_plan(montant: float) -> str | None:
    """None si le montant tient sous le plafond, sinon le message de refus."""
    try:
        f = plafond_nouveau_plan()
    except Exception as e:
        return f"❌ Budget réel illisible ({str(e)[:80]}) — réessaie dans un instant."
    if montant <= f["plafond"]:
        return None
    if f["plafond"] <= 0:
        return (f"❌ Aucun budget disponible pour un nouveau plan : {_detail(f)} = "
                f"{_eur(f['plafond'])}. Les plans existants ne sont pas modifiés. Pour en créer "
                "un : augmente ton capital total (page Réel) ou supprime un plan (page Plans). "
                "Attention : un plan défini en pourcentage du capital grandit avec lui.")
    return (f"❌ Budget trop élevé : {_eur(montant)} demandés, {_eur(f['plafond'])} disponibles "
            f"pour un nouveau plan ({_detail(f)}). Indique un montant ≤ {_eur(f['plafond'])}.")


def formater_recap(b: dict) -> str:
    return (
        f"📌 **Plan proposé** :\n"
        f"- Type : {b.get('plan_type')}\n"
        f"- Nom : {b.get('name')}\n"
        f"- Budget alloué : {b.get('allocated_budget', 0):.0f}€\n"
        f"- Objectif : +{b.get('target_return_percent', 0):.0f}% → {b.get('target_amount', 0):.0f}€\n"
        f"- Horizon : {b.get('time_horizon')}\n"
        f"- Vision : {b.get('vision', '')[:200]}\n"
        f"- Taille max/position : {b.get('max_position_size', 0):.0f}€"
    )
