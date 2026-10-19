"""
agents/vault/lecture.py — Lecture seule des bases pour la mémoire de trading (Phase 2, partie A).

data/registre.db et data/database.db ouverts en mode=ro. Tables lues : registre, positions et
portfolio_snapshots (paper) ; JAMAIS une table real_*. Les décisions du conseiller réel (origine
« conseiller », source « position_reelle ») sont écartées : elles désignent des actifs du
portefeuille réel. Jours et heures à Lisbonne (config.TIMEZONE), comme le registre (v1.7).
Historique depuis R2 : première ligne du registre le 06/10/2026.
"""

import json
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRE = os.path.join(RACINE, "data", "registre.db")
BASE = os.path.join(RACINE, "data", "database.db")
DEBUT = "2026-10-06"  # R2 (8b0fde3)
TABLES_LUES = ("registre", "positions", "portfolio_snapshots")


def _fuseau():
    try:
        import config
        return ZoneInfo(config.TIMEZONE)
    except Exception:
        return ZoneInfo("Europe/Lisbon")


def _connexion(chemin):
    if not os.path.exists(chemin):
        raise FileNotFoundError(chemin)
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def local(iso: str | None):
    """Horodatage ISO (UTC si sans fuseau) -> datetime à Lisbonne, ou None."""
    if not iso:
        return None
    d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=ZoneInfo("UTC"))).astimezone(_fuseau())


def _decision(r) -> dict | None:
    c = json.loads(r["contenu"] or "{}")
    if c.get("origine") != "cycle" or c.get("source") == "position_reelle":
        return None  # conseiller réel : actifs du portefeuille réel, hors du vault
    suite = c.get("suite") or {}
    d = local(r["horodatage"])
    return {"jour": d.date().isoformat(), "heure": d.strftime("%H:%M"), "cycle": r["cycle"],
            "passage_id": r["passage_id"], "ticker": r["ticker"], "decision": r["decision"],
            "style": r["style"], "score": r["score"], "confiance": r["confiance"], "prix": r["prix"],
            "source": c.get("source"), "resultat": suite.get("resultat"), "raisons": suite.get("raisons") or [],
            "position_id": suite.get("position_id") or r["position_id"],
            "pipeline": (c.get("pipeline") or {}).get("statut")}


def lire_registre(chemin: str = REGISTRE) -> dict:
    """Décisions BUY/SELL des cycles, passages, ancres, dernière watchlist enregistrée."""
    conn = _connexion(chemin)
    try:
        lignes = conn.execute(
            "SELECT horodatage, type, cycle, passage_id, ticker, decision, style, score, confiance, prix, "
            "position_id, contenu FROM registre WHERE horodatage >= ? ORDER BY id", (DEBUT,)).fetchall()
        parametres = conn.execute(
            "SELECT contenu FROM registre WHERE type = 'parametres' ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    decisions, passages, ancres = [], [], {}
    for r in lignes:
        if r["type"] == "decision" and r["decision"] in ("BUY", "SELL"):
            d = _decision(r)
            if d:
                decisions.append(d)
        elif r["type"] == "passage":
            c, d = json.loads(r["contenu"] or "{}"), local(r["horodatage"])
            passages.append({"jour": d.date().isoformat(), "heure": d.strftime("%H:%M"), "cycle": r["cycle"],
                             "duree_s": c.get("duree_s"), "ecrites": c.get("ecrites"), "erreurs": c.get("erreurs")})
        elif r["type"] == "ancre":
            c = json.loads(r["contenu"] or "{}")
            ancres[c.get("jour")] = {"empreinte": (c.get("derniere_empreinte") or "")[:16], "lignes": c.get("lignes"),
                                     "erreurs": (c.get("verification") or {}).get("erreurs")}
    watchlist = json.loads(parametres["contenu"]).get("WATCHLIST") if parametres else None
    return {"decisions": decisions, "passages": passages, "ancres": ancres, "watchlist": watchlist or [],
            "derniere": local(lignes[-1]["horodatage"]).strftime("%d/%m/%Y %H:%M") if lignes else None}


def lire_paper(chemin: str = BASE) -> dict:
    """Positions paper (ouvertes, ou ouvertes / fermées depuis R2) et instantanés quotidiens."""
    conn = _connexion(chemin)
    try:
        positions = [dict(r) for r in conn.execute(
            "SELECT id, ticker, asset_type, direction, status, entry_price, entry_date, quantity, invested_amount, "
            "stop_loss, target_1, exit_price, exit_date, pnl_euros, pnl_percent, confidence, entry_reason, exit_reason "
            "FROM positions WHERE status = 'OPEN' OR entry_date >= ? OR exit_date >= ? ORDER BY id", (DEBUT, DEBUT))]
        instantanes = {r["date"]: dict(r) for r in conn.execute(
            "SELECT date, cash, invested, total_value, daily_return_percent, cumulative_return_percent, "
            "open_positions_count FROM portfolio_snapshots WHERE date >= ? ORDER BY date", (DEBUT,))}
    finally:
        conn.close()
    for p in positions:
        p["entree"], p["sortie"] = local(p["entry_date"]), local(p["exit_date"])
    return {"positions": positions, "instantanes": instantanes}
