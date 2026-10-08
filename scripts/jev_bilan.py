"""
scripts/jev_bilan.py — Bilan de l'observation Jev (REGISTRE_CRITERES §7), LECTURE SEULE.

Lancement : .venv\\Scripts\\python.exe scripts\\jev_bilan.py

Avant la date de lecture (fin de la fenêtre de 12 semaines + 10 jours pour que
le dernier J+5 existe), n'affiche QUE des compteurs : aucun rendement (§0.3,
pas d'arrêt opportuniste). La base est ouverte en mode=ro : rien n'est écrit.
"""

import os
import sqlite3
import sys
from datetime import date, timedelta
from statistics import fmean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.jev.questions import MODELE, QUESTIONS_VERSION
from utils.jev_db import connexion_lecture, lire
from scripts import jev_bilan_calc as calc

N_MIN = 40                         # unités indépendantes Jev-acheter (§7)
FENETRE = timedelta(weeks=12)      # collecte à partir de la 1re observation
MATURATION = timedelta(days=10)    # le J+5 de la dernière observation doit exister
REDONDANCE = 0.80                  # part des Jev-acheter aussi BUY du moteur


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:+.2f} %"


def _ligne_ic(nom: str, unites: dict) -> tuple:
    m, bas, haut = calc.bootstrap_grappes(unites)
    print(f"  {nom:22s} n = {len(unites):3d}  moyenne {_pct(m)}  IC95 [{_pct(bas)} ; {_pct(haut)}]")
    return m, bas, haut


def compteurs(lignes: list[dict], obs: list[dict], debut: date | None, lecture: date | None) -> None:
    statuts = {s: sum(1 for l in lignes if l["statut"] == s) for s in ("ok", "erreur", "ecarte")}
    cl = calc.classes(obs)
    unites_acheter = {(calc.groupe(o["ticker"]), calc.semaine_iso(o["jour"])) for o in cl["jev_acheter"]}
    accords, comparables = calc.accord_regime(obs)
    erreurs = {}
    for l in lignes:
        if l["statut"] == "erreur":
            nom = (l.get("erreur") or "?").split(":")[0]
            erreurs[nom] = erreurs.get(nom, 0) + 1
    print(f"Questions {QUESTIONS_VERSION} — lignes : {len(lignes)} (ok {statuts['ok']}, "
          f"erreurs {statuts['erreur']}, écartées {statuts['ecarte']})")
    print(f"Observations (1re du jour par actif) : {len(obs)}, dont sans position paper : {len(cl['toutes'])}")
    print(f"Unités indépendantes Jev-acheter (groupe × semaine ISO) : {len(unites_acheter)} / minimum {N_MIN}")
    if erreurs:
        print("Erreurs par type : " + ", ".join(f"{k} {v}" for k, v in sorted(erreurs.items()))
              + " — si jev-1.13.0 n'est plus servi : test INTERROMPU (§7.6)")
    if comparables:
        print(f"Contrôle de lecture (pas un critère) : régime Jev = régime du moteur "
              f"dans {accords}/{comparables} cas ({accords / comparables:.0%})")
    ctrl = calc.controle_regime(obs)
    if ctrl["statut"] == "en_cours":
        print(f"Contrôle des {calc.JOURS_CONTROLE} premiers jours de bourse : {ctrl['jours']} jour(s) observé(s)")
    else:
        taux = ctrl["accords"] / ctrl["comparables"] if ctrl["comparables"] else 0.0
        print(f"Contrôle des {calc.JOURS_CONTROLE} premiers jours de bourse (jusqu'au {ctrl['jusqu_au']}) : "
              f"accord {taux:.0%} — " + ("OK" if ctrl["statut"] == "ok" else
              "ARRÊT : accord < 50 %, couper JEV_OBSERVE, corriger sous une version v2 (§7.2)"))
    if debut:
        print(f"Première observation : {debut} — fin de collecte : {debut + FENETRE} — lecture : {lecture}")


def verdict(n_acheter: int, ic_acheter: tuple, ic_diff: tuple, recouvrement: float | None) -> str:
    if n_acheter < N_MIN:
        return (f"NON CONCLUANT : {n_acheter} unités Jev-acheter < {N_MIN}. "
                f"Le seuil de 0,6 n'est PAS baissé ; rien ne change.")
    if not (ic_acheter[1] is not None and ic_acheter[1] > 0 and ic_diff[1] is not None and ic_diff[1] > 0):
        return "NON ATTEINT ou mitigé : rien ne change (§0.3)."
    if recouvrement is not None and recouvrement >= REDONDANCE:
        return (f"REDONDANT : {recouvrement:.0%} des Jev-acheter sont aussi des BUY du moteur ; "
                f"rien n'entre dans le vote.")
    return ("CRITÈRE ATTEINT : autorise seulement à rédiger un critère d'intégration au vote "
            "(nouveau commit du registre). Rien n'entre automatiquement dans le vote.")


def resultats(conn, obs: list[dict]) -> None:
    for o in obs:
        o["rendement"] = calc.rendement(conn, o["ticker"], o["jour"], o.get("prix"))
    cl = calc.classes(obs)
    u = {nom: calc.unites(v) for nom, v in cl.items()}
    print("\n== Critère principal (sans position paper, unités groupe × semaine ISO, J+5 net) ==")
    ic_a = _ligne_ic("Jev-acheter (p ≥ 0,6)", u["jev_acheter"])
    _ligne_ic("Jev-ne-rien-faire", u["jev_ne_rien_faire"])
    _ligne_ic("Moteur BUY", u["moteur_buy"])
    ic_d = calc.bootstrap_grappes_difference(u["jev_acheter"], u["jev_ne_rien_faire"])
    print(f"  Écart acheter − ne rien faire : {_pct(ic_d[0])}  IC95 [{_pct(ic_d[1])} ; {_pct(ic_d[2])}]")
    ic_m = calc.bootstrap_grappes_difference(u["jev_acheter"], u["moteur_buy"],
                                             graine=calc.GRAINE_ECART_MOTEUR)
    print(f"  Écart Jev-acheter − moteur BUY : {_pct(ic_m[0])}  IC95 [{_pct(ic_m[1])} ; {_pct(ic_m[2])}]")
    ja = cl["jev_acheter"]
    rec = (sum(1 for o in ja if o.get("decision_moteur") == "BUY") / len(ja)) if ja else None
    print(f"  Recouvrement Jev-acheter ∩ moteur BUY : {'—' if rec is None else f'{rec:.0%}'}")
    print(f"\nVERDICT : {verdict(len(u['jev_acheter']), ic_a, ic_d, rec)}")

    print("\n== Par groupe (descriptif, pas un critère) ==")
    for g in ("CRYPTO", "INDICES_US", "SEMIS_IA"):
        for nom in ("jev_acheter", "jev_ne_rien_faire", "moteur_buy"):
            v = [r for (gg, _), r in calc.unites(cl[nom]).items() if gg == g]
            print(f"  {g:11s} {nom:18s} n = {len(v):3d}  moyenne {_pct(fmean(v) if v else None)}")

    print("\n== Par actif et par jour (descriptif, pas un critère) ==")
    for t in sorted({o["ticker"] for o in cl["toutes"]}):
        lig = [f"  {t:9s}"]
        for nom in ("jev_acheter", "jev_ne_rien_faire", "moteur_buy"):
            v = [o["rendement"] for o in cl[nom] if o["ticker"] == t and o["rendement"] is not None]
            lig.append(f"{nom} {len(v):3d} × {_pct(fmean(v) if v else None)}")
        print("  ".join(lig))

    ouvertes = [o for o in obs if o.get("position_ouverte")]
    print(f"\n== Avec position paper ouverte (descriptif, hors critère) : {len(ouvertes)} observations ==")
    for a in ("ne_rien_faire", "conserver", "acheter"):
        v = [o["rendement"] for o in ouvertes if o.get("action_jev") == a and o["rendement"] is not None]
        print(f"  {a:14s} n = {len(v):3d}  moyenne {_pct(fmean(v) if v else None)}")


def main(aujourd_hui: date | None = None, conn=None) -> int:
    aujourd_hui = aujourd_hui or date.today()
    try:
        conn = conn or connexion_lecture()
    except sqlite3.OperationalError as e:
        print(f"Base inaccessible en lecture ({e}) : aucune observation à afficher.")
        return 1
    lignes = [l for l in lire(conn) if l["questions_version"] == QUESTIONS_VERSION]
    autres = sum(1 for l in lignes if l["statut"] == "ok" and l.get("modele") != MODELE)
    obs = calc.premieres_du_jour([l for l in lignes if l["statut"] != "ok" or l.get("modele") == MODELE],
                                 QUESTIONS_VERSION)
    debut = date.fromisoformat(obs[0]["jour"]) if obs else None
    lecture = debut + FENETRE + MATURATION if debut else None
    if debut:  # seules les observations de la fenêtre comptent
        obs = [o for o in obs if date.fromisoformat(o["jour"]) < debut + FENETRE]
    print("AlphaSignal — Bilan Jev (observation seule, paper) — lecture seule\n")
    compteurs(lignes, obs, debut, lecture)
    if autres:
        print(f"⚠️ {autres} ligne(s) ok d'un autre modèle que {MODELE} : exclues du critère")
    if lecture is None or aujourd_hui < lecture:
        print("\nAucun résultat avant la date de lecture (REGISTRE_CRITERES §0.3 et §7).")
        return 0
    resultats(conn, obs)
    print("\n⚠️ Paper trading uniquement : aucune conclusion ne s'applique au portefeuille réel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
