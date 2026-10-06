"""
agents/chat/_pnl_latent.py — P&L latent paper pour le chat, sans appel réseau
(Phase 4, TODO §8).

Chaque position est valorisée au dernier prix relevé par les cycles
(utils/dernier_prix.py). Sans prix, ou au-delà de config.CHAT_PRIX_AGE_MAX_MIN,
elle est « non disponible ». Règles : une valeur inconnue n'est jamais affichée
comme zéro, et une somme partielle n'est jamais présentée comme un total.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
from utils.dernier_prix import lire as lire_dernier_prix

NON_DISPO = "non disponible"


def nd(v, fmt: str = "{}") -> str:
    """Valeur formatée, ou « non disponible » si elle est inconnue (jamais 0)."""
    return NON_DISPO if v is None else fmt.format(v)


def _heure(d: datetime) -> str:
    try:
        return d.astimezone(ZoneInfo(config.TIMEZONE)).strftime("%Hh%M")
    except Exception:
        return d.strftime("%Hh%M UTC")


def _seance_precedente(prix: dict) -> str | None:
    """« 05/10 » si le cours date d'une séance antérieure au jour du relevé, à
    l'heure de la place (avant l'ouverture, week-end) ; None sinon."""
    try:
        cours = datetime.fromisoformat(prix["cours_a"])
        jour_releve = datetime.fromisoformat(prix["recupere_a"]).astimezone(cours.tzinfo).date()
        return cours.strftime("%d/%m") if cours.tzinfo and cours.date() < jour_releve else None
    except (KeyError, TypeError, ValueError):
        return None


def pnl_latent_paper(positions: list[dict], maintenant: datetime | None = None) -> dict:
    """P&L latent des positions qui ont un prix assez récent, et ce qui manque."""
    maintenant = maintenant or datetime.now(timezone.utc)
    total, releves, manquants, clotures, detail = 0.0, [], [], {}, {}
    for p in positions:
        prix = lire_dernier_prix(p["ticker"])
        releve = datetime.fromisoformat(prix["recupere_a"]) if prix else None
        if not prix or (maintenant - releve).total_seconds() > config.CHAT_PRIX_AGE_MAX_MIN * 60:
            manquants.append(p["ticker"])
            continue
        ecart = prix["prix"] - p["entry_price"]  # même formule que agents/paper_trader/portfolio.py
        pnl = (ecart if p["direction"] == "LONG" else -ecart) * p["quantity"]
        total += pnl
        releves.append(releve)
        seance = _seance_precedente(prix)
        if seance:
            clotures.setdefault(seance, []).append(p["ticker"])
        # Détail par position (page Overview) : pourcentage inconnu si rien d'investi, jamais 0
        detail[p.get("id", p["ticker"])] = {
            "prix": prix["prix"], "pnl": pnl, "releve": _heure(releve), "cloture_du": seance,
            "pnl_pct": pnl / p["invested_amount"] * 100 if p.get("invested_amount") else None}
    return {"total": total if releves else None, "complet": bool(positions) and not manquants,
            "nb_avec_prix": len(releves), "nb_positions": len(positions), "manquants": manquants,
            "releve_min": min(releves) if releves else None,
            "releve_max": max(releves) if releves else None, "clotures": clotures, "positions": detail}


def texte_pnl(info: dict | None) -> str:
    """Ligne « P&L latent » du prompt et du brouillon du chat."""
    if info is None:
        return NON_DISPO
    n, k = info["nb_positions"], info["nb_avec_prix"]
    if n == 0:
        return "aucune position ouverte"
    if k == 0:
        return (f"{NON_DISPO} (aucun prix relevé depuis moins de "
                f"{config.CHAT_PRIX_AGE_MAX_MIN} min pour les {n} positions)")
    hmin, hmax = _heure(info["releve_min"]), _heure(info["releve_max"])
    heure = f"prix de {hmin}" if hmin == hmax else f"prix relevés entre {hmin} et {hmax}"
    if info["complet"]:
        texte = f"{info['total']:+.2f}€ sur les {n} positions ({heure})"
    else:
        texte = (f"{info['total']:+.2f}€ sur {k} positions sur {n} seulement ({heure}) ; "
                 f"prix {NON_DISPO} pour {', '.join(info['manquants'])} : "
                 f"P&L latent total {NON_DISPO}")
    for seance, tickers in info["clotures"].items():
        texte += (f" ; {', '.join(tickers)} : cours de clôture du {seance}, "
                  f"pas de cotation plus récente au moment du relevé")
    return texte
