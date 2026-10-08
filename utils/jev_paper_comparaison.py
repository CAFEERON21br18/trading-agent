"""
utils/jev_paper_comparaison.py — Ligne de comparaison du dashboard : fantôme Jev et
paper actuel (REGISTRE_CRITERES §8.3). LECTURE SEULE, descriptif, pas un critère.

C'est la seule exception à l'interdiction d'afficher un rendement avant la lecture
du §7 : la valeur de chacun et son nombre de positions ouvertes, rien d'autre (ni
P&L par position, par actif ou par groupe, ni réalisé et latent séparés).
- Même fenêtre des deux côtés : depuis la première entrée du fantôme ; côté paper,
  les positions ouvertes ce jour-là ou après (jour de Lisbonne).
- Valeur = CAPITAL + P&L réalisé + P&L latent à la dernière clôture de `prices`,
  coûts aller-retour du §7.1 déduits des deux côtés. Côté paper, ces coûts ne
  servent qu'à cette ligne : ses tables ne changent pas.
- Une valeur inconnue (prix ou P&L manquant) vaut None, jamais 0.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
from scripts.jev_bilan_calc import cout

MENTION = "descriptif, pas un critère"


def _table_existe(conn, nom: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (nom,)).fetchone() is not None


def _derniere_cloture(conn, ticker: str) -> float | None:
    r = conn.execute("SELECT close FROM prices WHERE ticker = ? AND timeframe = '1d' AND close IS NOT NULL "
                     "ORDER BY timestamp DESC LIMIT 1", (ticker,)).fetchone()
    return float(r[0]) if r else None


def _jour_lisbonne(horodatage: str) -> str:
    """Jour de Lisbonne d'un horodatage ISO (UTC si sans fuseau)."""
    try:
        d = datetime.fromisoformat(horodatage)
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return d.astimezone(ZoneInfo(config.TIMEZONE)).date().isoformat()
    except (TypeError, ValueError):
        return str(horodatage)[:10]


def _cote(capital: float, positions: list[dict], conn) -> dict:
    """positions : {ticker, ouverte, sens (+1 / −1), entree, quantite, investi, pnl_realise, deduire_frais}."""
    total, manquants, ouvertes = capital, [], 0
    for p in positions:
        frais = cout(p["ticker"]) * p["investi"]
        if not p["ouverte"]:
            if p["pnl_realise"] is None:
                manquants.append(p["ticker"])
            else:
                total += p["pnl_realise"] - (frais if p["deduire_frais"] else 0)
            continue
        ouvertes += 1
        prix = _derniere_cloture(conn, p["ticker"])
        if prix is None:
            manquants.append(p["ticker"])
        else:
            total += p["sens"] * (prix - p["entree"]) * p["quantite"] - frais
    return {"valeur": None if manquants else round(total, 2), "positions_ouvertes": ouvertes,
            "prix_manquants": sorted(set(manquants))}


def _fantome(conn) -> list[dict]:
    rows = conn.execute("SELECT ticker, statut, prix_entree, quantite, montant_investi, pnl_net "
                        "FROM jev_paper_positions").fetchall()
    # pnl_net est déjà net des coûts du §7.1 (fantome_regles.resultat)
    return [{"ticker": r["ticker"], "ouverte": r["statut"] == "OPEN", "sens": 1, "entree": r["prix_entree"],
             "quantite": r["quantite"], "investi": r["montant_investi"], "pnl_realise": r["pnl_net"],
             "deduire_frais": False} for r in rows]


def _paper(conn, debut: str) -> list[dict]:
    if not _table_existe(conn, "positions"):
        return []
    rows = conn.execute("SELECT ticker, direction, status, entry_price, quantity, invested_amount, pnl_euros, "
                        "entry_date FROM positions").fetchall()
    # pnl_euros du paper est brut : les coûts du §7.1 sont déduits ici, pour cette ligne seulement
    return [{"ticker": r["ticker"], "ouverte": r["status"] == "OPEN",
             "sens": 1 if r["direction"] == "LONG" else -1, "entree": r["entry_price"],
             "quantite": r["quantity"], "investi": r["invested_amount"], "pnl_realise": r["pnl_euros"],
             "deduire_frais": True} for r in rows if _jour_lisbonne(r["entry_date"]) >= debut]


def comparaison(conn) -> dict:
    """Ligne du §8.3. debut None tant que le fantôme n'a acheté aucune position."""
    vide = {"mention": MENTION, "debut": None, "capital_depart": None, "fantome": None, "paper": None}
    if not _table_existe(conn, "jev_paper_positions"):
        return vide
    debut = conn.execute("SELECT MIN(jour_entree) FROM jev_paper_positions").fetchone()[0]
    if debut is None:
        return vide
    capital = float(config.CAPITAL)
    return {**vide, "debut": debut, "capital_depart": capital,
            "fantome": _cote(capital, _fantome(conn), conn), "paper": _cote(capital, _paper(conn, debut), conn)}
