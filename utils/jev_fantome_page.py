"""
utils/jev_fantome_page.py — Page « Fantôme Jev » du dashboard (REGISTRE_CRITERES §8.3,
v1.5). LECTURE SEULE (connexion mode=ro de l'appelant), descriptif, pas un critère.

Quatre blocs :
1. positions ouvertes : P&L latent à la dernière clôture de `prices`, NET des coûts
   du §7.1 comme l'en-tête (1 000 € + total des fermées + total des latents = valeur
   du fantôme) ; date de la 5e barre (sortie du §8.2), estimée tant qu'elle n'existe pas ;
2. positions fermées : P&L net de coûts (€ et %), total cumulé ;
3. dernière observation : utils/jev_fantome_jour.py ;
4. en-tête : ligne de comparaison de la page d'accueil, positions, refus par motif.
Une valeur inconnue (prix manquant) vaut None, affichée « non disponible », jamais 0.
Aucune métrique du §7 : ni rendement des observations non achetées, ni moyenne par
groupe ou par classe.
"""

from datetime import date, timedelta

from agents.jev.fantome import barres_horizon
from scripts.jev_bilan_calc import GROUPES, HORIZON, cout, groupe
from utils.jev_fantome_jour import derniere_observation
from utils.jev_paper_comparaison import comparaison, derniere_cloture_datee, table_existe


def _arrondi(x, n: int = 2):
    return None if x is None else round(x, n)


def date_sortie_prevue(barres: list, jour_entree: str, ticker: str) -> dict:
    """Date de la 5e barre datée du jour d'entrée ou après (calcul du fantôme, §8.2).
    Connue si les 5 barres sont en base ; sinon, les barres manquantes sont projetées
    après la dernière connue : jours calendaires pour les cryptos (-USD), du lundi au
    vendredi pour le reste (jours fériés inconnus, d'où « estimée »)."""
    if len(barres) >= HORIZON:
        return {"barre": barres[HORIZON - 1][0], "estimee": False}
    jour = date.fromisoformat(barres[-1][0]) + timedelta(days=1) if barres else date.fromisoformat(jour_entree)
    manquantes = HORIZON - len(barres)
    while True:
        if ticker.endswith("-USD") or jour.weekday() < 5:
            manquantes -= 1
            if manquantes == 0:
                return {"barre": jour.isoformat(), "estimee": True}
        jour += timedelta(days=1)


def _groupe(ticker: str) -> str | None:
    """Groupe du §0.1, None pour un actif compté seul."""
    g = groupe(ticker)
    return g if g in GROUPES else None


def _ouverte(conn, p: dict) -> dict:
    derniere = derniere_cloture_datee(conn, p["ticker"])
    latent = None
    if derniere is not None:  # coûts du §7.1 déduits, comme l'en-tête
        latent = p["quantite"] * (derniere[1] - p["prix_entree"]) - cout(p["ticker"]) * p["montant_investi"]
    return {"ticker": p["ticker"], "groupe": _groupe(p["ticker"]), "jour_entree": p["jour_entree"],
            "p_acheter": p["p_acheter"], "conviction_niveau": p["conviction_niveau"], "facteur": p["facteur"],
            "montant_investi": _arrondi(p["montant_investi"]), "prix_entree": p["prix_entree"],
            "dernier_prix": derniere[1] if derniere else None,
            "jour_dernier_prix": derniere[0] if derniere else None,
            "pnl_latent": _arrondi(latent),
            "pnl_latent_pct": None if latent is None else _arrondi(latent / p["montant_investi"] * 100),
            "sortie": date_sortie_prevue(barres_horizon(conn, p["ticker"], p["jour_entree"]),
                                         p["jour_entree"], p["ticker"])}


def _fermee(p: dict) -> dict:
    return {"ticker": p["ticker"], "groupe": _groupe(p["ticker"]), "jour_entree": p["jour_entree"],
            "prix_entree": p["prix_entree"], "barre_sortie": p["barre_sortie"], "jour_sortie": p["jour_sortie"],
            "prix_sortie": p["prix_sortie"], "montant_investi": _arrondi(p["montant_investi"]),
            "pnl_net": _arrondi(p["pnl_net"]),
            "pnl_pct": None if p["pnl_pct"] is None else _arrondi(p["pnl_pct"] * 100)}


def _total(lignes: list[dict], cle: str) -> dict:
    """Somme des montants investis et du P&L ; P&L None si une valeur manque (jamais 0)."""
    investi = sum(l["montant_investi"] for l in lignes)
    valeurs = [l[cle] for l in lignes]
    pnl = None if None in valeurs else sum(valeurs)
    return {"positions": len(lignes), "montant_investi": _arrondi(investi), "pnl": _arrondi(pnl),
            "pnl_pct": None if pnl is None or not investi else _arrondi(pnl / investi * 100)}


def _refus_par_motif(conn) -> dict:
    if not table_existe(conn, "jev_paper_journal"):
        return {}
    rows = conn.execute("SELECT motif, COUNT(*) FROM jev_paper_journal WHERE evenement = 'refus' "
                        "GROUP BY motif ORDER BY COUNT(*) DESC, motif").fetchall()
    return {r[0]: r[1] for r in rows}


def page(conn) -> dict:
    """Les quatre blocs de la page ; rien n'est écrit."""
    entete = comparaison(conn)
    positions = []
    if table_existe(conn, "jev_paper_positions"):
        positions = [dict(r) for r in conn.execute(
            "SELECT * FROM jev_paper_positions ORDER BY jour_entree, ticker, id").fetchall()]
    ouvertes = [_ouverte(conn, p) for p in positions if p["statut"] == "OPEN"]
    fermees = sorted((_fermee(p) for p in positions if p["statut"] == "CLOSED"),
                     key=lambda f: (f["barre_sortie"] or "", f["ticker"]), reverse=True)
    refus = _refus_par_motif(conn)
    return {"mention": entete["mention"],
            "entete": {**entete, "positions_ouvertes": len(ouvertes), "positions_fermees": len(fermees),
                       "refus_total": sum(refus.values()), "refus_par_motif": refus},
            "ouvertes": {"positions": ouvertes, "total": _total(ouvertes, "pnl_latent")},
            "fermees": {"positions": fermees, "total": _total(fermees, "pnl_net")},
            "jour": derniere_observation(conn)}
