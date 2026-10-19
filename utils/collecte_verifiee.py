"""
utils/collecte_verifiee.py — Collecte des prix vérifiée et relancée (REGISTRE_CRITERES v1.9, §9.8 a).

Cause (17/10/2026) : la collecte du rattrapage a tourné pendant que Yahoo était injoignable ;
aucune barre écrite, puis le rapport du jour a bloqué toute nouvelle tentative.

- collecter_et_verifier() (cycle quotidien) : après la collecte, compte les actifs qui ont leur
  barre 1d du jour attendu (date_attendue). Sous 80 %, nouvel essai, 3 essais au plus à 5 minutes
  d'intervalle. Un téléchargement non vide compte aussi comme réussi (marché fermé ce jour-là :
  jour férié). Chaque essai commence par une sonde sur un seul actif : en panne réseau, l'essai
  échoue en quelques secondes au lieu de 69 téléchargements en délai dépassé.
- filet_tactical() : si la dernière barre 1d a été ÉCRITE il y a plus de 30 h, relance une collecte,
  au plus une fois par heure, jamais pendant le cycle quotidien (verrou « collecte » partagé).
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone

from utils import database
from utils.lock_manager import acquerir_lock, est_actif, liberer_lock
from utils.logger import get_logger

logger = get_logger(__name__)

SEUIL_PART = 0.8
ESSAIS = 3
ATTENTE_S = 5 * 60
AGE_FILET_H = 30
INTERVALLE_FILET = timedelta(hours=1)
VERROU = "collecte"
ETAT_FILET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "cache", "filet_collecte.json")


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


_dormir = time.sleep  # remplaçable dans les tests


def date_attendue(ticker: str, maintenant: datetime) -> date:
    """Crypto : la barre du jour (UTC). Autres : la dernière séance de semaine avant aujourd'hui."""
    jour = maintenant.astimezone(timezone.utc).date()
    if ticker.endswith("-USD"):
        return jour
    d = jour - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _actifs_1d(watchlist: dict) -> list[str]:
    return [t for actifs in watchlist.values() for t, info in actifs.items()
            if "1d" in ((info or {}).get("timeframes") or ["1d"])]


def verifier(watchlist: dict, resume: dict | None, maintenant: datetime) -> dict:
    """{part, ok_n, total, manquants, barres_1d} : part des actifs à jour après une collecte."""
    actifs = _actifs_1d(watchlist)
    resume = resume or {}
    manquants = []
    conn = database.get_connection()
    try:
        for t in actifs:
            row = conn.execute("SELECT MAX(timestamp) FROM prices WHERE ticker = ? AND timeframe = '1d'",
                               (t,)).fetchone()
            derniere = date.fromisoformat(str(row[0])[:10]) if row and row[0] else None
            telecharge = (resume.get(t) or {}).get("1d") is not None
            if not ((derniere and derniere >= date_attendue(t, maintenant)) or telecharge):
                manquants.append(t)
    finally:
        conn.close()
    total = len(actifs)
    barres = sum((resume.get(t) or {}).get("1d") or 0 for t in actifs)
    return {"part": (total - len(manquants)) / total if total else 0.0, "ok_n": total - len(manquants),
            "total": total, "manquants": manquants, "barres_1d": barres}


def _collecter_watchlist(watchlist: dict) -> dict:
    from scripts.fetch_data import collecter_toute_la_watchlist
    return collecter_toute_la_watchlist(watchlist)


def _sonder(watchlist: dict) -> bool:
    """Un seul téléchargement 1d (première crypto, sinon premier actif) : Yahoo répond-il ?"""
    from scripts.fetch_data import recuperer_ohlcv_yfinance
    actifs = _actifs_1d(watchlist)
    cible = next((t for t in actifs if t.endswith("-USD")), actifs[0] if actifs else "BTC-USD")
    return not recuperer_ohlcv_yfinance(cible, "1d").empty


def _sous_verrou(fonction, *args, attendre_s: float = 900, dormir=time.sleep):
    """Exécute sous le verrou « collecte » ; attend la fin d'un filet en cours (15 min au plus)."""
    debut = time.monotonic()
    try:
        while not acquerir_lock(VERROU):
            if time.monotonic() - debut > attendre_s:
                logger.warning("Verrou « collecte » toujours pris après 15 min : collecte lancée sans verrou")
                return fonction(*args)
            dormir(10)
    except OSError as e:
        logger.error(f"Verrou « collecte » impossible ({e}) : collecte lancée sans verrou")
        return fonction(*args)
    try:
        return fonction(*args)
    finally:
        liberer_lock(VERROU)


def collecter_et_verifier(charger=None, collecter=None, sonder=None, dormir=None, maintenant=None) -> dict:
    """Cycle quotidien : collecte vérifiée, 3 essais au plus. {ok, essais, part, manquants, raison}."""
    if charger is None:
        from utils.helpers import charger_watchlist as charger
    collecter, sonder = collecter or _collecter_watchlist, sonder or _sonder
    dormir, maintenant = dormir or _dormir, maintenant or _maintenant
    watchlist = charger() or {}
    if not _actifs_1d(watchlist):
        return {"ok": False, "essais": 0, "part": 0.0, "manquants": [], "raison": "watchlist vide ou illisible"}
    for essai in range(1, ESSAIS + 1):
        resume = _sous_verrou(collecter, watchlist, dormir=dormir) if sonder(watchlist) else {}
        v = verifier(watchlist, resume, maintenant())
        logger.info(f"Collecte, essai {essai}/{ESSAIS} : {v['ok_n']}/{v['total']} actifs à jour "
                    f"({v['barres_1d']} barres 1d écrites ou réparées)")
        if v["part"] >= SEUIL_PART:
            return {**v, "ok": True, "essais": essai, "raison": ""}
        if essai < ESSAIS:
            logger.warning(f"Collecte incomplète ({v['part']:.0%} < {SEUIL_PART:.0%}) : nouvel essai dans "
                           f"{ATTENTE_S // 60} min")
            dormir(ATTENTE_S)
    raison = (f"{v['ok_n']}/{v['total']} actifs à jour après {ESSAIS} essais (seuil {SEUIL_PART:.0%}) ; "
              f"manquants : {', '.join(v['manquants'][:8])}")
    logger.error(f"❌ Collecte des prix en échec : {raison}. Rapport du jour NON écrit : le rattrapage de "
                 f"12h retentera.")
    return {**v, "ok": False, "essais": ESSAIS, "raison": raison}


def age_derniere_ecriture_h(maintenant: datetime) -> float | None:
    """Heures depuis la dernière ÉCRITURE d'une barre 1d (created_at), None si aucune barre."""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT MAX(created_at) FROM prices WHERE timeframe = '1d'").fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    ecrite = datetime.fromisoformat(str(row[0])).replace(tzinfo=timezone.utc)
    return (maintenant - ecrite).total_seconds() / 3600


def _dernier_filet() -> datetime | None:
    try:
        with open(ETAT_FILET, encoding="utf-8") as f:
            return datetime.fromisoformat(json.load(f)["dernier_essai"])
    except (OSError, ValueError, KeyError):
        return None


def filet_tactical(charger=None, collecter=None, sonder=None, maintenant=None) -> str:
    """Tactical : relance une collecte si la dernière barre 1d écrite a plus de 30 h. Ne lève jamais."""
    try:
        collecter, sonder = collecter or _collecter_watchlist, sonder or _sonder
        t = (maintenant or _maintenant)()
        age = age_derniere_ecriture_h(t)
        if age is None or age <= AGE_FILET_H:
            return "inutile"
        if est_actif("daily"):
            return "quotidien en cours"
        dernier = _dernier_filet()
        if dernier and t - dernier < INTERVALLE_FILET:
            return "attente"
        os.makedirs(os.path.dirname(ETAT_FILET), exist_ok=True)
        with open(ETAT_FILET, "w", encoding="utf-8") as f:
            json.dump({"dernier_essai": t.isoformat()}, f)  # avant la collecte : une fois par heure au plus
        if charger is None:
            from utils.helpers import charger_watchlist as charger
        watchlist = charger() or {}
        if not sonder(watchlist):
            logger.warning(f"Filet de collecte : dernière barre 1d écrite il y a {age:.0f} h, Yahoo ne répond pas")
            return "sonde en échec"
        if not acquerir_lock(VERROU):
            return "verrou pris"
        try:
            resume = collecter(watchlist)
        finally:
            liberer_lock(VERROU)
        n = sum((r or {}).get("1d") or 0 for r in (resume or {}).values())
        logger.warning(f"Filet de collecte : dernière barre 1d écrite il y a {age:.0f} h, collecte relancée "
                       f"({n} barres 1d écrites ou réparées)")
        return "relancee"
    except Exception as e:
        logger.error(f"Filet de collecte : {e}")
        return "erreur"
