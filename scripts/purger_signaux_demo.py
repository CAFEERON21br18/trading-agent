"""
scripts/purger_signaux_demo.py — Purge des signaux de démonstration (docs/TODO.md, signal_results).

Le 15/04/2026, le bloc __main__ de performance_tracker.py a tourné sur la vraie
base : SIG-0001 à SIG-0005, dont 3 clôturés dans signal_results (winrate 66,7 %,
profit factor 3,35), lus ensuite par le Budget Manager, le pipeline et le chat.

Usage : python scripts/purger_signaux_demo.py [--appliquer]
Sans option : à blanc, base en lecture seule. Avec --appliquer, dans cet ordre, toute
vérification en échec arrête le script sans rien supprimer :
  0. generer_signal_id corrigé (plus grand numéro + 1), contrôlé sur une base temporaire :
     sinon le prochain signal reprendrait un numéro existant (UNIQUE) et ne serait pas enregistré ;
  1. copie de data/database.db vers data/sauvegardes/database_avant_purge_demo_<AAAAMMJJ>.db
     (ignorée par git, jamais écrasée, contrôlée : intégrité et nombre de lignes) ;
  2. SIG-0001 à SIG-0005 identiques à la démo (demo_performance.py), résultats de 0001 à 0003 seulement ;
  3. suppression dans signal_results puis signals, en une seule transaction ;
  4. memory/performance_tracker.md régénéré (mettre_a_jour_performance_md).
Avant --appliquer : redémarrer la tâche \\AlphaSignal\\dashboard. Sa route run-analysis
enregistre des signaux avec le generer_signal_id chargé au démarrage du dashboard.
"""

import os
import sys
import math
import argparse
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from utils import database
from agents.trade_journalist import journalist, performance_tracker
from agents.trade_journalist.demo_performance import SIGNAUX_DEMO, CLOTURES_DEMO

IDS = [f"SIG-{i:04d}" for i in range(1, len(SIGNAUX_DEMO) + 1)]
PLACE = ",".join("?" * len(IDS))
COLONNES = ("ticker", "direction", "confidence", "price_at_signal", "stop_loss",
            "target_1", "target_2", "timeframe", "source_agents", "reason")
DOSSIER_SAUVEGARDES = os.path.join(RACINE, "data", "sauvegardes")


def correction_en_place() -> bool:
    """generer_signal_id sur une base temporaire où SIG-0002 a été supprimé : attendu SIG-0004."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, \
            mock.patch.object(database, "DB_PATH", os.path.join(d, "controle.db")):
        conn = sqlite3.connect(database.DB_PATH)
        conn.execute("CREATE TABLE signals (signal_id TEXT UNIQUE NOT NULL)")
        conn.executemany("INSERT INTO signals VALUES (?)", [("SIG-0001",), ("SIG-0003",)])
        conn.commit(); conn.close()
        return journalist.generer_signal_id() == "SIG-0004"  # COUNT(*) + 1 donnerait SIG-0003


def resultats_attendus() -> dict:
    """signal_id → (prix de sortie, pnl_pct, correct, leçon), calculés comme cloturer_signal."""
    attendus = {}
    for rang, sortie, lecon in CLOTURES_DEMO:
        entree, sens = SIGNAUX_DEMO[rang][3], SIGNAUX_DEMO[rang][1]
        pnl = (sortie - entree) / entree * 100 if sens == "LONG" else (entree - sortie) / entree * 100
        attendus[IDS[rang]] = (sortie, pnl, "OUI" if pnl > 0 else ("NON" if pnl < 0 else "PARTIEL"), lecon)
    return attendus


def ecarts(conn) -> list[str]:
    """Différences entre la base et les valeurs de la démo ; liste vide si tout correspond."""
    e = []
    lus = {r[0]: r[1:] for r in conn.execute(
        f"SELECT signal_id, {', '.join(COLONNES)} FROM signals WHERE signal_id IN ({PLACE})", IDS)}
    for sid, attendu in zip(IDS, SIGNAUX_DEMO):
        if sid not in lus:
            e.append(f"{sid} absent de signals")
            continue
        e += [f"{sid}.{c} = {l!r}, attendu {a!r}" for c, a, l in zip(COLONNES, attendu, lus[sid]) if a != l]
    res = {r[0]: r[1:] for r in conn.execute(
        f"SELECT signal_id, exit_price, pnl_pct, correct, lesson FROM signal_results WHERE signal_id IN ({PLACE})", IDS)}
    attendus = resultats_attendus()
    for sid in IDS:
        lu, at = res.get(sid), attendus.get(sid)
        if (lu is None) != (at is None):
            e.append(f"{sid} : {'absent de' if lu is None else 'résultat inattendu dans'} signal_results")
        elif lu is not None and (lu[0] != at[0] or lu[1] is None or not math.isclose(lu[1], at[1], rel_tol=1e-9)
                                 or tuple(lu[2:]) != at[2:]):
            e.append(f"{sid} : résultat {tuple(lu)}, attendu {at}")
    return e


def copie_ignoree(chemin: str) -> bool:
    """La copie ne doit jamais être suivie par git (dépôt public)."""
    try:
        return subprocess.run(["git", "check-ignore", "-q", chemin], cwd=RACINE).returncode == 0
    except Exception:
        return False


def sauvegarder(dest: str) -> None:
    """Copie de la base (API backup, source en lecture seule), contrôlée. Lève si invalide."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    src = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    src.backup(dst)
    compte = lambda c: [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("signals", "signal_results")]
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and compte(src) == compte(dst)
    src.close(); dst.close()
    if not ok:
        raise RuntimeError(f"sauvegarde {dest} invalide")


def supprimer() -> tuple[int, int]:
    """Revérifie puis supprime, dans une seule transaction. Lève (rien supprimé) en cas d'écart."""
    conn = sqlite3.connect(database.DB_PATH, timeout=30, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        e = ecarts(conn)
        if e:
            raise RuntimeError("valeurs différentes de la démo : " + " ; ".join(e))
        n_res = conn.execute(f"DELETE FROM signal_results WHERE signal_id IN ({PLACE})", IDS).rowcount
        n_sig = conn.execute(f"DELETE FROM signals WHERE signal_id IN ({PLACE})", IDS).rowcount
        if (n_res, n_sig) != (len(CLOTURES_DEMO), len(IDS)):
            raise RuntimeError(f"{n_res} résultat(s) et {n_sig} signal(aux) supprimables, "
                               f"attendu {len(CLOTURES_DEMO)} et {len(IDS)}")
        conn.execute("COMMIT")
        return n_res, n_sig
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def afficher_table_par_actif() -> None:
    """Lignes de la table « Performance par actif » de memory/performance_tracker.md."""
    try:
        with open(performance_tracker.PERFORMANCE_FILE, encoding="utf-8") as f:
            texte = f.read().split("## Performance par actif", 1)[-1]
        table = [l for l in texte.splitlines() if l.startswith("|")]
    except OSError:
        table = []
    for l in table[2:] or ["(aucune ligne)"]:  # sans l'en-tête ni la ligne de séparation
        print(f"      {l}")


def main(appliquer: bool) -> int:
    print(f"Base : {database.DB_PATH}\n")
    correction = correction_en_place()
    print(f"[0] generer_signal_id corrigé (plus grand numéro + 1) : {'oui' if correction else 'NON'}")
    lecture = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
    lignes = lecture.execute(f"""SELECT s.signal_id, s.ticker, s.direction, s.price_at_signal, s.timestamp,
                                        r.exit_price, r.pnl_pct FROM signals s LEFT JOIN signal_results r
                                 ON r.signal_id = s.signal_id WHERE s.signal_id IN ({PLACE}) ORDER BY s.id""", IDS).fetchall()
    e = ecarts(lecture)
    n_sig, n_res, n_max = lecture.execute("""SELECT (SELECT COUNT(*) FROM signals), (SELECT COUNT(*) FROM signal_results),
                                                    (SELECT MAX(CAST(SUBSTR(signal_id, 5) AS INTEGER)) FROM signals)""").fetchone()
    lecture.close()
    dest = os.path.join(DOSSIER_SAUVEGARDES, f"database_avant_purge_demo_{datetime.now():%Y%m%d}.db")
    ignoree, existe = copie_ignoree(dest), os.path.exists(dest)
    print(f"[1] sauvegarde {dest} : {'ignorée' if ignoree else 'NON ignorée'} par git"
          f"{' ; EXISTE DÉJÀ, ne sera pas écrasée' if existe else ''}")
    print(f"[2] valeurs identiques à la démo : {'oui' if not e else 'NON'}")
    for x in e:
        print(f"      - {x}")
    for sid, t, d, p, ts, sortie, pnl in lignes:
        fin = f"résultat : sortie {sortie}, {pnl:+.2f} %" if sortie is not None else "sans résultat"
        print(f"      {sid}  {t:8s} {d:5s} entrée {p:<9}  {ts[:19]}  {fin}")
    print(f"[3] à supprimer : {sum(l[5] is not None for l in lignes)} ligne(s) de signal_results (sur {n_res}), "
          f"{len(lignes)} de signals (sur {n_sig}) ; prochain identifiant ensuite : SIG-{(n_max or 0) + 1:04d}")
    print("[4] memory/performance_tracker.md, « Performance par actif » aujourd'hui :")
    afficher_table_par_actif()
    if not appliquer:
        print("\nÀ blanc : rien n'a été écrit. Pour purger : redémarrer \\AlphaSignal\\dashboard, puis --appliquer.")
        return 0
    arret = ("generer_signal_id non corrigé" if not correction else "copie non ignorée par git" if not ignoree
             else "sauvegarde du jour déjà présente" if existe else "valeurs différentes de la démo" if e else None)
    if arret:
        print(f"\nARRÊT : {arret}. Rien n'a été copié ni supprimé.")
        return 1
    sauvegarder(dest)
    print(f"\nSauvegarde contrôlée : {dest}")
    try:
        n_res_sup, n_sig_sup = supprimer()
    except Exception as ex:
        print(f"ARRÊT : {ex}. Rien n'a été supprimé.")
        return 1
    print(f"Supprimé : {n_res_sup} ligne(s) de signal_results, {n_sig_sup} de signals.")
    performance_tracker.mettre_a_jour_performance_md()
    stats = performance_tracker.calculer_stats_globales(nb_derniers=20)
    print(f"Régénéré : {performance_tracker.PERFORMANCE_FILE} (calculer_stats_globales(20) : "
          f"{stats.get('nb_trades')} trade(s)) ; « Performance par actif » :")
    afficher_table_par_actif()
    print(f"Prochain identifiant : {journalist.generer_signal_id()}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge SIG-0001 à SIG-0005 (démo du 15/04/2026).")
    parser.add_argument("--appliquer", action="store_true", help="écrire (sinon à blanc, base en lecture seule)")
    sys.exit(main(parser.parse_args().appliquer))
