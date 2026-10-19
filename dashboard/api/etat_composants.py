"""
dashboard/api/etat_composants.py — Vue temps réel de la carte (Phase 3) : état de chaque composant.

Lu SEULEMENT dans des sources existantes, en lecture seule : tâches planifiées (etat_taches),
logs/<tâche>.log et <tâche>_errors.log (etat_journaux), tables de database.db et registre.db
(etat_tables). Quelle source pour quel composant : déduit du code (etat_code, champ sources_etat
de la carte), rien n'est écrit à la main. Les trois sources sont lues en parallèle, chacune avec
son budget de temps : lente ou en panne, elle manque à la réponse sans jamais la faire échouer.

États : actif (exécution dans la fenêtre attendue : 2 × la période de sa tâche planifiée, sinon de
la plus lente des tâches dont les journaux le citent, sinon 24 h ; ou tâche en cours), en erreur (tâche en échec, ERROR dans son
dernier passage, erreur sur la dernière ligne d'une table qu'il remplit), inactif (exécution plus
ancienne, ou tâche désactivée), jamais exécuté (des sources, aucune trace), inconnu (seule source :
les tâches, illisibles), pas de source d'état. Messages d'erreur masqués (utils/secret_mask.py).
"""

import os
from datetime import datetime, timedelta, timezone

from dashboard.api import etat_journaux, etat_tables, etat_taches
from utils.bloc_borne import executer_en_parallele
from utils.secret_mask import masquer_secrets

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOSSIER_LOGS = os.path.join(RACINE, "logs")
BASES = {"database.db": os.path.join(RACINE, "data", "database.db"),
         "registre.db": os.path.join(RACINE, "data", "registre.db")}
BUDGETS_S = {"taches": 8, "journaux": 5, "tables": 4}
FENETRE = timedelta(hours=24)
MARGE = timedelta(minutes=2)  # durée d'un passage, en plus de 2 × la période
_HEURE = "%Y-%m-%d %H:%M:%S"


def _local(heure: str) -> datetime:
    return datetime.strptime(heure, _HEURE).astimezone()


def _court(d) -> str:
    return d.astimezone().strftime("%d/%m %H:%M") if d else "?"


def _activite(journaux, modules, tache_vers_comp, depuis: str) -> dict:
    """Par composant : dernière ligne (et sa tâche), passages des 24 h, début du dernier passage,
    dernière erreur (heure, tâche, logger, message), d'après le logger de chaque ligne."""
    def composant(nom, tache):
        if nom == "__main__":
            return tache_vers_comp.get(tache)
        chemin = nom.replace(".", "/")
        return next((modules[c] for c in (chemin + ".py", chemin + "/__init__.py", f"scripts/{nom}.py")
                     if c in modules), None)

    act = {}
    vide = lambda: {"derniere": "", "tache": None, "passages": set(), "debut": "", "erreur": None, "taches": set()}
    for tache, r in journaux.items():
        for nom, info in r["par_logger"].items():
            c = composant(nom, tache)
            if c is None:
                continue
            a = act.setdefault(c, vide())
            a["taches"].add(tache)
            if info["derniere"] > a["derniere"]:
                a["derniere"], a["tache"] = info["derniere"], tache
            for i in info["passages"]:
                debut = r["passages"][i]
                a["debut"] = max(a["debut"], debut)
                if debut >= depuis:
                    a["passages"].add((tache, i))
        for nom, (heure, message) in r["erreurs"].items():
            c = composant(nom, tache)
            if c is not None and (act.setdefault(c, vide())["erreur"] or ("",))[0] < heure:
                act[c]["erreur"] = (heure, tache, nom, message)
    return act


def _etat_composant(noeud, sources, taches, act, tables, maintenant, lu_ok) -> dict:
    c, details, dates = noeud["id"], [], []
    noms = sources["taches"].get(c, [])
    infos = [taches[t] for t in noms if taches and t in taches]
    for t in noms:
        if taches is None:
            details.append(f"Tâche {etat_taches.DOSSIER}{t} : inconnu (tâches planifiées illisibles)")
        elif t in taches:
            i = taches[t]
            dates.append(i["dernier"])
            details.append(f"Tâche {etat_taches.DOSSIER}{t} : {i['etat']}, lancée le {_court(i['dernier'])} "
                           f"(code {i['code']}{', échec' if i['en_erreur'] else ''})"
                           + (f", prochaine {_court(i['prochain'])}" if i["prochain"] else ""))
    a = act.get(c)
    journalise = any(m["chemin"] in sources["journalises"] for m in noeud["modules"])
    if a and a["derniere"]:
        dates.append(_local(a["derniere"]))
        details.append(f"Journaux ({', '.join(sorted(a['taches']))}) : {len(a['passages'])} passage(s) "
                       f"sur 24 h, dernière ligne {_court(_local(a['derniere']))}")
    elif journalise:
        details.append("Journaux : aucune ligne de ses modules dans logs/")
    erreur = None
    if a and a["erreur"]:
        heure, tache, nom, message = a["erreur"]
        erreur = masquer_secrets(f"{nom} — {message}")[:240]
        details.append(f"Dernière erreur {_court(_local(heure))} ({tache}.log) : {erreur}")
    lignes = [(t, tables[t]) for t in sources["tables_inserees"].get(c, []) if t in tables]
    for t, v in lignes:
        d = datetime.fromisoformat(v["derniere"]) if v["derniere"] else None
        dates.append(d)
        details.append(f"Table {t} ({v['base']}) : dernière ligne {_court(d) if d else 'aucune'}, "
                       f"{v['lignes_24h']} sur 24 h"
                       + (f" ({v['passages_24h']} passages)" if v.get("passages_24h") is not None else "")
                       + (f", erreur : {masquer_secrets(v['erreur'])[:160]}" if v["erreur"] else ""))
    derniere = max((d for d in dates if d), default=None)
    passages = [len(a["passages"])] if a and a["passages"] else []
    passages += [v["passages_24h"] for _, v in lignes if v.get("passages_24h") is not None]
    if passages:
        executions, unite = max(passages), "passages"
    elif lignes:
        executions, unite = sum(v["lignes_24h"] or 0 for _, v in lignes), "lignes écrites"
    else:
        executions, unite = None, None
    # Fenêtre attendue : sa propre tâche, sinon la plus lente des tâches où il écrit (un composant qui
    # ne tourne pas à chaque tactical tourne au moins une fois par passage quotidien), sinon 24 h
    periodes = [i["periode"] for i in infos if i["periode"]]
    if not periodes and a and taches:
        lentes = [taches[t]["periode"] for t in a["taches"] if t in taches and taches[t]["periode"]]
        periodes = [max(lentes)] if lentes else []
    fenetre = 2 * min(periodes) + MARGE if periodes else FENETRE
    en_erreur = any(i["en_erreur"] for i in infos) or any(v["erreur"] for _, v in lignes) \
        or bool(a and a["erreur"] and a["erreur"][0] >= a["debut"])
    illisibles = (noms and taches is None) or (journalise and not lu_ok["journaux"]) \
        or (sources["tables_inserees"].get(c) and not lu_ok["tables"])
    if not lu_ok["journaux"] and journalise:
        details.append("Journaux : non lus (délai dépassé ou erreur de lecture)")
    if not lu_ok["tables"] and sources["tables_inserees"].get(c):
        details.append("Tables : non lues (délai dépassé ou base verrouillée)")
    if not (noms or journalise or a or sources["tables_inserees"].get(c)):
        etat = "pas de source d'état"
    elif en_erreur:
        etat = "en erreur"
    elif any(i["etat"] == "Running" for i in infos):
        etat = "actif"
    elif any(i["etat"] == "Disabled" for i in infos):
        etat = "inactif"
    elif derniere is None:
        etat = "inconnu" if illisibles else "jamais exécuté"
    else:
        etat = "actif" if maintenant - derniere <= fenetre else "inactif"
    return {"etat": etat, "derniere_execution": derniere.isoformat() if derniere else None,
            "executions_24h": executions, "unite": unite, "fenetre_min": round(fenetre.total_seconds() / 60),
            "erreur": erreur, "details": details}


def _etat_table(nom, tables, maintenant) -> dict:
    v = tables.get(nom)
    if v is None or not v.get("colonne"):
        return {"etat": "pas de source d'état", "derniere_execution": None, "executions_24h": None,
                "unite": None, "erreur": None, "details": []}
    d = datetime.fromisoformat(v["derniere"]) if v["derniere"] else None
    etat = "jamais exécuté" if d is None else "actif" if maintenant - d <= FENETRE else "inactif"
    return {"etat": etat, "derniere_execution": v["derniere"], "executions_24h": v["lignes_24h"],
            "unite": "lignes écrites", "erreur": None,
            "details": [f"Table {nom} ({v['base']}, colonne {v['colonne']}) : dernière ligne "
                        f"{_court(d) if d else 'aucune'}, {v['lignes_24h']} sur 24 h"]}


def etat_des_composants(carte, maintenant=None, dossier_logs=DOSSIER_LOGS, bases=BASES) -> dict:
    """État de chaque nœud de la carte (dict sérialisable en JSON). Ne lève pas sur une source."""
    maintenant = maintenant or datetime.now(timezone.utc)
    debut = maintenant - FENETRE
    se = carte["sources_etat"]
    sources = {"taches": se["taches"], "tables_inserees": se["tables_inserees"],
               "journalises": set(se["modules_journalises"])}
    voulues = {t for ts in se["tables_inserees"].values() for t in ts} | \
              {n["libelle"] for n in carte["noeuds"] if n["type"] == "table"}
    lu = executer_en_parallele(BUDGETS_S, {
        "taches": etat_taches.lire_taches,
        "journaux": lambda: etat_journaux.lire_journaux(dossier_logs, debut.astimezone().strftime(_HEURE)),
        "tables": lambda: etat_tables.lire_tables(bases, voulues, debut)})
    modules = {m["chemin"]: n["id"] for n in carte["noeuds"] for m in n["modules"]}
    tache_vers_comp = {t: c for c, ts in se["taches"].items() for t in ts}
    act = _activite(lu["journaux"] or {}, modules, tache_vers_comp, debut.astimezone().strftime(_HEURE))
    tables = lu["tables"] or {}
    lu_ok = {k: v is not None for k, v in lu.items()}
    composants = {}
    for n in carte["noeuds"]:
        if n["type"] == "composant":
            composants[n["id"]] = _etat_composant(n, sources, lu["taches"], act, tables, maintenant, lu_ok)
        elif n["type"] == "table":
            composants[n["id"]] = _etat_table(n["libelle"], tables, maintenant)
        else:
            composants[n["id"]] = _etat_table(None, {}, maintenant)
    return {"genere_le": maintenant.isoformat(timespec="seconds"), "fenetre_h": 24,
            "sources": {k: ("ok" if v is not None else "inconnu" if k == "taches" else "indisponible")
                        for k, v in lu.items()},
            "composants": composants}
