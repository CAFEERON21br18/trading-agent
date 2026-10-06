"""
utils/registre_manuel.py — Interventions manuelles du dashboard dans le registre (Phase 4, R3).

Chaque intervention est un passage de cycle « manuel », avec son déclencheur (la route) :
- trailing stop activé ou désactivé sur une position paper : une ligne « reevaluation » ;
- watchlist modifiée : la ligne de clôture du passage porte les actifs ajoutés, retirés,
  et si l'ordre a changé (la composition entre aussi dans l'empreinte des paramètres) ;
- routine lancée depuis le dashboard (run-analysis) : voir agents/orchestrator.py.
Ces interventions sont un facteur de confusion pour les analyses (TODO §13).
Rien ici ne lève d'exception vers une route : un échec est seulement journalisé.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.registre import composition_watchlist
from utils.registre_cycles import ouvrir, clore, noter_evenement

logger = get_logger(__name__)

ROUTE_TRAILING = "POST /api/positions/<id>/trailing-stop"
ROUTE_WATCHLIST = "POST /api/settings/watchlist"
ROUTE_WATCHLIST_ACTIF = "POST /api/settings/watchlist/actif"  # P14 : un seul actif
ROUTE_ANALYSE = "POST /api/run-analysis"


def _position(position_id: int) -> dict | None:
    from utils.database import get_connection
    conn = get_connection()
    try:
        r = conn.execute("SELECT id, ticker, status, trailing_stop_active, trailing_stop_price "
                         "FROM positions WHERE id = ?", (position_id,)).fetchone()
    finally:
        conn.close()
    return dict(zip(("id", "ticker", "status", "trailing_stop_active", "trailing_stop_price"), r)) if r else None


def noter_trailing(position_id: int, active: bool, resultat: dict) -> None:
    """Après la route : enregistre l'activation ou la désactivation, si la position a été modifiée."""
    try:
        pos = _position(position_id)
        if not (resultat or {}).get("ok") or pos is None:
            return  # rien n'a changé (position introuvable, fermée, ATR indisponible)
        passage = ouvrir("manuel", declencheur=ROUTE_TRAILING, action="trailing_stop")
        if passage is None:
            return
        try:
            details = ({"stop_initial": resultat.get("initial_stop"), "atr": resultat.get("atr"),
                        "atr_multiplier": resultat.get("atr_multiplier")} if active
                       else {"stop_conserve": pos["trailing_stop_price"], "statut_position": pos["status"]})
            noter_evenement(passage, pos, "TRAILING_ACTIVE" if active else "TRAILING_DESACTIVE", None, details)
        finally:
            clore(passage)
    except Exception as e:
        logger.warning(f"Registre : intervention trailing #{position_id} non enregistrée : {e}")


def _a_plat(compo: dict) -> list:
    return [t for tickers in compo.values() if isinstance(tickers, list) for t in tickers]


def noter_watchlist(avant: dict, route: str = ROUTE_WATCHLIST) -> None:
    """Après l'écriture de data/watchlist.json : différence de composition avec avant."""
    try:
        apres = composition_watchlist()
        a, b = _a_plat(avant), _a_plat(apres)
        passage = ouvrir("manuel", declencheur=route, action="watchlist")
        if passage is not None:
            clore(passage, details={
                "ajoutes": [t for t in b if t not in a], "retires": [t for t in a if t not in b],
                "ordre_modifie": [t for t in a if t in b] != [t for t in b if t in a],
                "actifs_avant": len(a), "actifs_apres": len(b),
                "composition": [[cat, tickers] for cat, tickers in apres.items()]})  # R3b : ordre des catégories gardé
    except Exception as e:
        logger.warning(f"Registre : modification de la watchlist non enregistrée : {e}")
