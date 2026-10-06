"""
scripts/reparer_prix_null.py — Réparation des barres à prix NULL de la table prices (Phase 4).

Re-télécharge via yfinance, avec les paramètres de scripts/fetch_data.py
(auto_adjust=True), les dates précises dont un prix (open, high, low, close)
est NULL, et affiche la liste avant / après.

Usage :
  python scripts/reparer_prix_null.py              # simulation : base en lecture seule
  python scripts/reparer_prix_null.py --appliquer  # écrit les valeurs retrouvées

Garanties :
- aucune ligne supprimée ; une ligne sans valeur de remplacement reste telle quelle ;
- seules les lignes encore NULL sont modifiées (UPDATE … WHERE … IS NULL) ;
- cohérence avec la série déjà en base : les barres voisines re-téléchargées
  sont comparées à celles en base. Leur rapport (dividendes ou splits survenus
  depuis l'enregistrement, auto_adjust) est appliqué à la barre réparée s'il
  est le même des deux côtés (écart ≤ ECART_MAX_VOISINS) ; sinon : « à vérifier » ;
- le volume déjà en base est conservé.
"""

import sys
import os
import argparse
import sqlite3
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from utils.database import DB_PATH, get_connection
from utils.valeurs import nombre_ou_none, ohlc_ou_none
from scripts.fetch_data import TIMEFRAME_CONFIG

ECART_MAX_VOISINS = 0.001   # 0,1 % entre le rapport de la veille et celui du lendemain
MARGE_JOURS = 10            # fenêtre de téléchargement autour des dates à réparer
NULL_SQL = "(open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL)"


def lignes_null(conn) -> list[dict]:
    rows = conn.execute(f"""SELECT id, ticker, timeframe, timestamp, open, high, low, close, volume
                            FROM prices WHERE {NULL_SQL} ORDER BY ticker, timeframe, timestamp""")
    return [dict(zip(("id", "ticker", "timeframe", "timestamp", "open", "high", "low", "close", "volume"), r))
            for r in rows]


def _voisine(conn, l: dict, sens: str):
    """Barre valide la plus proche déjà en base, avant (sens « < ») ou après (« > »)."""
    ordre = "DESC" if sens == "<" else "ASC"
    return conn.execute(f"""SELECT timestamp, close FROM prices
                            WHERE ticker = ? AND timeframe = ? AND timestamp {sens} ? AND NOT {NULL_SQL}
                            ORDER BY timestamp {ordre} LIMIT 1""",
                        (l["ticker"], l["timeframe"], l["timestamp"])).fetchone()


def telecharger(ticker: str, timeframe: str, debut, fin) -> dict:
    """{timestamp au format de la base : ligne pandas}, mêmes paramètres que fetch_data."""
    import yfinance as yf
    cfg = TIMEFRAME_CONFIG[timeframe]
    df = yf.download(ticker, start=debut, end=fin, interval=cfg["interval"],
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        return {}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return {str(ts): row for ts, row in df.iterrows()}


def proposer(conn, l: dict, telecharge: dict) -> dict:
    """Valeurs de remplacement pour une ligne NULL, ou la raison de ne pas réparer."""
    ohlc = ohlc_ou_none(telecharge[l["timestamp"]]) if l["timestamp"] in telecharge else None
    if ohlc is None:
        return {"statut": "à vérifier : aucune valeur valide re-téléchargée"}
    rapports = []
    for sens in ("<", ">"):
        v = _voisine(conn, l, sens)
        brut = telecharge.get(v[0]) if v else None
        close_dl = nombre_ou_none(brut.get("Close")) if brut is not None else None
        if v and close_dl:
            rapports.append(v[1] / close_dl)
    if not rapports:
        return {"statut": "à vérifier : aucune barre voisine comparable", "ohlc_brut": ohlc}
    if max(rapports) - min(rapports) > ECART_MAX_VOISINS * min(rapports):
        return {"statut": f"à vérifier : rapports voisins incohérents {rapports}", "ohlc_brut": ohlc}
    r = sum(rapports) / len(rapports)
    return {"statut": "à réparer", "rapport": r, "nb_voisins": len(rapports),
            "ohlc": tuple(x * r for x in ohlc),
            "volume": nombre_ou_none(telecharge[l["timestamp"]].get("Volume"))}


def _fmt(vals) -> str:
    return "/".join("NULL" if v is None else f"{v:.4f}" for v in vals)


def main(appliquer: bool) -> int:
    lecture = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    lignes = lignes_null(lecture)
    print(f"{len(lignes)} ligne(s) avec un prix NULL dans {DB_PATH}\n")
    groupes: dict = {}
    for l in lignes:
        groupes.setdefault((l["ticker"], l["timeframe"]), []).append(l)
    propositions = []
    for (ticker, tf), ls in groupes.items():
        dates = [pd.Timestamp(l["timestamp"][:10]) for l in ls]
        try:
            telecharge = telecharger(ticker, tf, min(dates) - timedelta(days=MARGE_JOURS),
                                     max(dates) + timedelta(days=MARGE_JOURS))
        except Exception as e:
            telecharge = {}
            print(f"  ⚠️ téléchargement {ticker} [{tf}] en échec : {e}")
        propositions += [(l, proposer(lecture, l, telecharge)) for l in ls]
    lecture.close()

    print(f"{'ticker':9s} {'tf':3s} {'barre':19s}  {'avant O/H/L/C':34s}  {'après O/H/L/C':44s}  rapport   statut")
    for l, p in propositions:
        apres = _fmt(p["ohlc"]) if "ohlc" in p else "—"
        rapport = f"{p['rapport']:.5f} ({p['nb_voisins']})" if "rapport" in p else "—"
        print(f"{l['ticker']:9s} {l['timeframe']:3s} {l['timestamp']:19s}  "
              f"{_fmt((l['open'], l['high'], l['low'], l['close'])):34s}  {apres:44s}  {rapport:9s} {p['statut']}")
    a_reparer = [(l, p) for l, p in propositions if p["statut"] == "à réparer"]
    print(f"\n{len(a_reparer)} réparable(s), {len(propositions) - len(a_reparer)} à vérifier (laissées telles quelles).")
    if not appliquer:
        print("Simulation : rien n'a été écrit. Relancer avec --appliquer pour écrire.")
        return 0

    conn = get_connection()
    ecrites = 0
    for l, p in a_reparer:
        cur = conn.execute(f"""UPDATE prices SET open = ?, high = ?, low = ?, close = ?,
                                   volume = COALESCE(volume, ?)
                               WHERE id = ? AND {NULL_SQL}""", (*p["ohlc"], p["volume"], l["id"]))
        ecrites += cur.rowcount
    conn.commit()
    print(f"\n{ecrites} ligne(s) réparée(s). État après écriture :")
    for l, _ in a_reparer:
        r = conn.execute("SELECT open, high, low, close, volume FROM prices WHERE id = ?", (l["id"],)).fetchone()
        print(f"  {l['ticker']:9s} {l['timestamp']:19s}  {_fmt(tuple(r)[:4])}  volume {r[4]}")
    restantes = conn.execute(f"SELECT COUNT(*) FROM prices WHERE {NULL_SQL}").fetchone()[0]
    conn.close()
    print(f"Lignes encore NULL : {restantes}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Répare les barres à prix NULL de la table prices.")
    parser.add_argument("--appliquer", action="store_true", help="écrire (sinon simulation en lecture seule)")
    sys.exit(main(parser.parse_args().appliquer))
