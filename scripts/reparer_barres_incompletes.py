"""
scripts/reparer_barres_incompletes.py — Barres enregistrées avant leur clôture puis figées (Phase 4, P10).

Avant P10, la collecte de 06h30 UTC enregistrait la barre encore en cours (jour
des cryptos 24/7 et des futures, semaine en cours, heure en cours) et
l'INSERT OR IGNORE la figeait. Ce script re-télécharge ces barres, avec les
paramètres de scripts/fetch_data.py, et les remplace par la barre complète.

Usage :
  python scripts/reparer_barres_incompletes.py                 # simulation : base en lecture seule
  python scripts/reparer_barres_incompletes.py --detail f.csv  # + détail barre par barre
  python scripts/reparer_barres_incompletes.py --appliquer     # sauvegarde horodatée, puis écriture

Garanties : aucune ligne supprimée. Une barre n'est remplacée que si la barre
re-téléchargée est valide, si son ouverture correspond à celle en base (rapport
dans ±2 %, appliqué aux prix pour rester sur la base d'ajustement de la série)
et si son plus haut et son plus bas englobent ceux de la barre partielle
(tolérance 0,2 %) ; sinon « à vérifier », la ligne reste telle quelle.
Barre encore en cours : ignorée. Avant toute écriture : sauvegarde de la base
hors du dépôt, contrôlée (intégrité, nombre de lignes), sinon rien n'est écrit.
"""

import sys
import os
import csv
import argparse
import sqlite3
import statistics
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from utils.database import DB_PATH, get_connection
from utils.valeurs import nombre_ou_none, ohlc_ou_none
from scripts.fetch_data import TIMEFRAME_CONFIG

TOLERANCE_RAPPORT = 0.02    # ouverture : base d'ajustement différente (dividendes) au plus ±2 %
TOLERANCE_RANGE = 0.002     # la barre complète doit englober la partielle, à 0,2 % près
MARGE = timedelta(days=10)
DOSSIER_SAUVEGARDES = os.path.join(os.path.dirname(os.path.dirname(DB_PATH)), "..", "trading-agent-sauvegardes")
COLONNES = ("id", "ticker", "timeframe", "timestamp", "open", "high", "low", "close", "volume", "created_at")


def barres_figees(conn) -> list[dict]:
    """Barres enregistrées avant leur clôture, aujourd'hui closes, sans prix NULL (traités par P9)."""
    lignes = []
    for tf, cfg in TIMEFRAME_CONFIG.items():
        d = cfg["duree"]
        lignes += [dict(zip(COLONNES, r)) for r in conn.execute(f"""
            SELECT {', '.join(COLONNES)} FROM prices
            WHERE timeframe = ? AND created_at < datetime(timestamp, ?) AND datetime(timestamp, ?) <= datetime('now')
              AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
            ORDER BY ticker, timestamp""", (tf, d, d))]
    return lignes


def telecharger(ticker: str, timeframe: str, debut, fin) -> dict:
    """{timestamp au format de la base : ligne pandas}, mêmes paramètres que fetch_data.
    1d et 1wk : même période que la collecte (découpage des semaines identique) ;
    1h : dates précises, la collecte ne remontant qu'à 60 jours."""
    import yfinance as yf
    cfg = TIMEFRAME_CONFIG[timeframe]
    plage = {"start": debut, "end": fin} if cfg["interval"] == "1h" else {"period": cfg["period"]}
    df = yf.download(ticker, interval=cfg["interval"], auto_adjust=True, progress=False, **plage)
    if df is None or df.empty:
        return {}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return {str(ts): row for ts, row in df.iterrows()}


def proposer(l: dict, telecharge: dict) -> dict:
    brut = telecharge.get(l["timestamp"])
    ohlc = ohlc_ou_none(brut) if brut is not None else None
    if ohlc is None:
        return {"statut": "à vérifier : barre non re-téléchargée"}
    r = l["open"] / ohlc[0]
    if abs(r - 1) > TOLERANCE_RAPPORT:
        return {"statut": f"à vérifier : ouverture différente (rapport {r:.4f})"}
    o, h, lo, c = (x * r for x in ohlc)
    if h < l["high"] * (1 - TOLERANCE_RANGE) or lo > l["low"] * (1 + TOLERANCE_RANGE):
        return {"statut": "à vérifier : la barre complète n'englobe pas la partielle"}
    vol = nombre_ou_none(brut.get("Volume"))
    if max(abs(a - b) / b for a, b in zip((o, h, lo, c), (l["open"], l["high"], l["low"], l["close"]))) < 1e-6:
        return {"statut": "déjà complète"}
    return {"statut": "à réparer", "rapport": r, "ohlc": (o, h, lo, c), "volume": vol}


def sauvegarder_base() -> str:
    """Copie horodatée et contrôlée de la base, hors du dépôt. Lève une exception si invalide."""
    os.makedirs(DOSSIER_SAUVEGARDES, exist_ok=True)
    dest = os.path.abspath(os.path.join(DOSSIER_SAUVEGARDES, f"database_{datetime.now():%Y%m%d_%H%M%S}_avant_P10.db"))
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    src.backup(dst)
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and \
        src.execute("SELECT COUNT(*) FROM prices").fetchone() == dst.execute("SELECT COUNT(*) FROM prices").fetchone()
    src.close(); dst.close()
    if not ok:
        raise RuntimeError(f"sauvegarde {dest} invalide : aucune écriture")
    return dest


def _ecart_range(l, ohlc=None) -> float:
    h, lo = (ohlc[1], ohlc[2]) if ohlc else (l["high"], l["low"])
    return (h - lo) / l["open"] * 100


def resumer(propositions: list) -> None:
    print(f"{'ticker':9s} {'tf':3s} {'barres':>6s} {'réparer':>7s} {'complètes':>9s} {'vérifier':>8s}   "
          f"écart haut-bas médian avant → après   |Δ clôture| médian")
    groupes: dict = {}
    for l, p in propositions:
        groupes.setdefault((l["ticker"], l["timeframe"]), []).append((l, p))
    for (t, tf), lp in groupes.items():
        rep = [(l, p) for l, p in lp if p["statut"] == "à réparer"]
        n_comp = sum(p["statut"] == "déjà complète" for _, p in lp)
        av = statistics.median(_ecart_range(l) for l, _ in rep) if rep else 0
        ap = statistics.median(_ecart_range(l, p["ohlc"]) for l, p in rep) if rep else 0
        dc = statistics.median(abs(p["ohlc"][3] / l["close"] - 1) * 100 for l, p in rep) if rep else 0
        print(f"{t:9s} {tf:3s} {len(lp):6d} {len(rep):7d} {n_comp:9d} {len(lp) - len(rep) - n_comp:8d}   "
              f"{av:8.2f} % → {ap:6.2f} %{'':14s}{dc:6.2f} %")


def main(appliquer: bool, detail: str | None) -> int:
    lecture = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    lignes = barres_figees(lecture)
    lecture.close()
    print(f"{len(lignes)} barre(s) enregistrée(s) avant leur clôture puis figée(s) dans {DB_PATH}\n")
    groupes: dict = {}
    for l in lignes:
        groupes.setdefault((l["ticker"], l["timeframe"]), []).append(l)
    propositions = []
    for (ticker, tf), ls in groupes.items():
        dates = [pd.Timestamp(l["timestamp"][:10]) for l in ls]
        try:
            telecharge = telecharger(ticker, tf, min(dates) - MARGE, max(dates) + MARGE)
        except Exception as e:
            telecharge = {}
            print(f"  ⚠️ téléchargement {ticker} [{tf}] en échec : {e}")
        propositions += [(l, proposer(l, telecharge)) for l in ls]
    resumer(propositions)
    if detail:
        with open(detail, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id", "ticker", "tf", "barre", "enregistrée", "avant O/H/L/C/V", "après O/H/L/C/V", "rapport", "statut"])
            for l, p in propositions:
                w.writerow([l["id"], l["ticker"], l["timeframe"], l["timestamp"], l["created_at"],
                            [l["open"], l["high"], l["low"], l["close"], l["volume"]],
                            [*p["ohlc"], p["volume"]] if "ohlc" in p else "", p.get("rapport", ""), p["statut"]])
        print(f"\nDétail barre par barre : {detail}")
    a_reparer = [(l, p) for l, p in propositions if p["statut"] == "à réparer"]
    print(f"\n{len(a_reparer)} à réparer, {sum(p['statut'] == 'déjà complète' for _, p in propositions)} déjà complète(s), "
          f"{sum(p['statut'].startswith('à vérifier') for _, p in propositions)} à vérifier (laissées telles quelles).")
    if not appliquer:
        print("Simulation : rien n'a été écrit. Relancer avec --appliquer pour écrire (sauvegarde automatique avant).")
        return 0

    print(f"Sauvegarde : {sauvegarder_base()}")
    conn = get_connection()
    ecrites = 0
    for l, p in a_reparer:
        cur = conn.execute("""UPDATE prices SET open = ?, high = ?, low = ?, close = ?,
                                  volume = COALESCE(?, volume), created_at = datetime('now')
                              WHERE id = ? AND created_at = ?""", (*p["ohlc"], p["volume"], l["id"], l["created_at"]))
        ecrites += cur.rowcount
    conn.commit()
    conn.close()
    lecture = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    print(f"{ecrites} barre(s) réparée(s). Barres encore figées incomplètes : {len(barres_figees(lecture))}")
    lecture.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Répare les barres enregistrées avant leur clôture.")
    parser.add_argument("--appliquer", action="store_true", help="écrire (sinon simulation en lecture seule)")
    parser.add_argument("--detail", help="fichier CSV du détail barre par barre")
    a = parser.parse_args()
    sys.exit(main(a.appliquer, a.detail))
