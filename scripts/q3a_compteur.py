"""
scripts/q3a_compteur.py — Compteur de la question 3.a (REGISTRE_CRITERES §3.a, v1.7), LECTURE SEULE.

Lancement : .venv\\Scripts\\python.exe scripts\\q3a_compteur.py
            .venv\\Scripts\\python.exe scripts\\q3a_compteur.py --constat logs\\task_tactical.log

Avant la lecture du 03/11/2026, n'affiche QUE des compteurs (§0.3) : couples examinés par semaine
ISO depuis R2 (06/10/2026), couples en repli Prudent à part, minimum requis et dates. Le script ne
lit ni prix, ni facteur, ni verdict. data/registre.db est ouvert en mode=ro : rien n'est écrit.

Couple examiné (v1.7) : (actif, jour de Lisbonne, action) d'une décision BUY ou SELL normale
d'origine « cycle », hors décisions sans données, dont le pipeline a été exécuté ou servi par le
cache. Un couple qui n'a eu que des replis Prudent est compté à part, hors du minimum.

--constat : même comptage sur les logs du tactical du constat du §3, jusqu'au commit c4908bb
(06/10/2026 18:58:50, heure de la tour = Lisbonne). Ces logs n'enregistrent pas l'action d'une
décision examinée : le couple y est donc (actif, jour).
"""

import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN = os.path.join(RACINE, "data", "registre.db")  # même fichier que utils/registre.CHEMIN

LISBONNE = ZoneInfo("Europe/Lisbon")
R2 = date(2026, 10, 6)           # mise en service de R2
LECTURE = date(2026, 11, 3)      # 4 semaines (§0.4)
ECHEANCE = date(2026, 12, 1)     # 8 semaines
N_MIN = 40                       # couples examinés ; les replis Prudent n'y entrent pas
STATUTS_EXAMINES = ("execute", "cache")
FIN_CONSTAT = "2026-10-06 18:58:50"
_TAILLE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) \| INFO +\| agents\.decision_engine \| "
                     r"Taille (\S+) ajustée par pipeline : [\d.]+ → [\d.]+ \((.*)$")


def jour_lisbonne(horodatage: str) -> date:
    """Horodatage ISO du registre (UTC) → date à Lisbonne."""
    t = datetime.fromisoformat(horodatage)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(LISBONNE).date()


def decisions_du_registre(conn) -> list[dict]:
    """Décisions retenues par la v1.7, réduites à {ticker, jour, action, statut du pipeline}."""
    out = []
    for horodatage, ticker, decision, style, prix, contenu in conn.execute(
            "SELECT horodatage, ticker, decision, style, prix, contenu FROM registre "
            "WHERE type = 'decision' ORDER BY id"):
        if decision not in ("BUY", "SELL") or style != "normal" or prix is None:
            continue  # prix vide : décision sans données (§0.1, v1.1)
        c = json.loads(contenu or "{}")
        if c.get("origine") != "cycle" or (c.get("suite") or {}).get("resultat") == "sans_donnees":
            continue
        jour = jour_lisbonne(horodatage)
        if jour >= R2:
            out.append({"ticker": ticker, "jour": jour, "action": decision,
                        "statut": (c.get("pipeline") or {}).get("statut")})
    return out


def decisions_du_constat(lignes, fin: str = FIN_CONSTAT) -> list[dict]:
    """Lignes « Taille X ajustée par pipeline » du tactical jusqu'à fin ; action inconnue (None) ;
    « Pipeline indisponible » = repli Prudent."""
    out = []
    for l in lignes:
        m = _TAILLE.match(l) if "ajustée par pipeline" in l else None
        if m and f"{m[1]} {m[2]}" <= fin:
            out.append({"ticker": m[3], "jour": date.fromisoformat(m[1]), "action": None,
                        "statut": "prudent" if m[4].startswith("Pipeline indisponible") else "execute"})
    return out


def couples(decisions: list[dict]) -> tuple[set, set]:
    """(couples examinés, couples qui n'ont eu que des replis Prudent)."""
    cle = lambda d: (d["ticker"], d["jour"], d["action"])
    examines = {cle(d) for d in decisions if d["statut"] in STATUTS_EXAMINES}
    prudents = {cle(d) for d in decisions if d["statut"] == "prudent"} - examines
    return examines, prudents


def par_semaine(examines: set, prudents: set) -> dict:
    """{« AAAA-Sxx » : (couples examinés, couples en repli Prudent seul)}, semaine ISO du jour."""
    out: dict = {}
    for i, ensemble in enumerate((examines, prudents)):
        for _, jour, _ in ensemble:
            a, s, _ = jour.isocalendar()
            out.setdefault(f"{a}-S{s:02d}", [0, 0])[i] += 1
    return {k: tuple(v) for k, v in sorted(out.items())}


def afficher(examines: set, prudents: set, lignes: int) -> None:
    print("AlphaSignal — Compteur de la question 3.a (REGISTRE_CRITERES §3.a, v1.7) — lecture seule\n")
    print(f"Décisions BUY ou SELL normales d'origine cycle lues : {lignes} (information)")
    print("Semaine ISO   couples examinés   couples en repli Prudent seul")
    for semaine, (e, p) in par_semaine(examines, prudents).items():
        print(f"  {semaine}     {e:6d}             {p:6d}")
    print(f"Depuis R2 ({R2:%d/%m/%Y}) : {len(examines)} couple(s) examiné(s), "
          f"{len(prudents)} couple(s) en repli Prudent seul (hors minimum)")
    print(f"Minimum requis : {N_MIN} couples examinés")
    print(f"Lecture prévue : {LECTURE:%d/%m/%Y} ; échéance : {ECHEANCE:%d/%m/%Y}")
    print("Compteurs seulement, comme le veut le §0.3 avant la lecture.")


def main(argv: list[str] | None = None, conn=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--constat"] and len(argv) == 2:
        with open(argv[1], encoding="utf-8", errors="replace") as f:
            examines, prudents = couples(decisions_du_constat(f))
        print(f"Constat du §3 (logs du tactical jusqu'au {FIN_CONSTAT}, action non enregistrée) : "
              f"{len(examines)} couple(s) examiné(s), {len(prudents)} en repli Prudent seul")
        return 0
    try:
        conn = conn or sqlite3.connect(f"file:{CHEMIN}?mode=ro", uri=True)
        decisions = decisions_du_registre(conn)
    except sqlite3.Error as e:
        print(f"Registre inaccessible en lecture ({e}) : rien à compter.")
        return 1
    examines, prudents = couples(decisions)
    afficher(examines, prudents, len(decisions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
