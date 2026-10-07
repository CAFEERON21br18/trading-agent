"""
dashboard/api/topology_incoherences.py — Incohérences calculées sur la carte de l'agent (Phase 3).

Chaque règle part des nœuds et liens déjà construits (topology_build) ; aucune
liste d'incohérences n'est écrite à la main. Seule la référence TODO de
chaque règle vient de topology_composants.TODO_INCOHERENCES.
"""

from dashboard.api import topology_composants as tc
from dashboard.api import topology_sources as ts

EXPLORATION = ("explorer.", "explorers.base", "queue")


def _cibles(liens, source, types=None):
    return {l["cible"] for l in liens if l["source"] == source and (types is None or l["type"] in types)}


def _noms(ids):
    """Libellés lisibles des composants (« Collecte des prix » plutôt que fetch_data)."""
    return ", ".join(tc.COMPOSANTS[i][0] if i in tc.COMPOSANTS else i.split(":")[-1] for i in sorted(ids))


def _incoherence(ident, titre, detail, noeuds, preuves=None):
    return {"id": ident, "titre": titre, "detail": detail, "noeuds": sorted(set(noeuds)),
            "preuves": preuves or [], "todo": tc.TODO_INCOHERENCES.get(ident)}


def _explorateurs_sans_prix(noeuds, liens):
    """Les explorateurs alimentent la queue, mais aucun composant d'exploration n'écrit dans prices."""
    explo = [n["id"] for n in noeuds if n["id"].startswith(EXPLORATION)]
    if not any("queue" in _cibles(liens, e) for e in explo):
        return None
    ecrivains = [l for l in liens if l["cible"] == "table:prices" and l["type"] == "ecrit"]
    if any(l["source"].startswith(EXPLORATION) for l in ecrivains):
        return None
    # Chemin d'une découverte : cycles qui lisent la queue et analysent, puis leurs analyseurs de prix
    consommateurs = [n["id"] for n in noeuds if n["groupe"] == "cycles"
                     and {"queue", "decision_engine"} <= _cibles(liens, n["id"])]
    lecteurs = sorted({l["cible"] for l in liens if l["source"] == "table:prices"}
                      & {c for k in consommateurs for c in _cibles(liens, k)})
    explo += consommateurs
    return _incoherence(
        "explorateurs_sans_prix", "Les découvertes des explorateurs n'ont pas de prix",
        "Les explorateurs remplissent la queue, mais seul(e) "
        f"{_noms({l['source'] for l in ecrivains}) or 'aucun composant'} écrit "
        "dans prices : l'analyse d'un ticker de la queue ne trouve aucune barre (HOLD, score 0).",
        explo + ["table:prices"] + [l["source"] for l in ecrivains] + lecteurs,
        [p for l in ecrivains for p in l["preuves"]])


def _cycles_queue_sans_analyse(noeuds, liens):
    """Un cycle qui lit la queue sans lien vers le Decision Engine."""
    trouves = []
    for n in noeuds:
        if n["groupe"] != "cycles" or n["id"] == "dashboard":
            continue
        cibles = _cibles(liens, n["id"])
        if "queue" in cibles and "decision_engine" not in cibles:
            preuves = [p for l in liens if l["source"] == n["id"] and l["cible"] == "queue"
                       for p in l["preuves"]]
            trouves.append(_incoherence(
                "cycle_lit_queue_sans_analyse", f"{n['libelle']} lit la queue sans l'analyser",
                f"Le cycle {n['libelle']} importe la queue mais n'a aucun lien vers le Decision Engine.",
                [n["id"], "queue"], preuves))
    return trouves


def _explorateurs_plusieurs_cycles(noeuds, liens):
    """Explorateurs lancés par plusieurs cycles."""
    cycles = {n["id"] for n in noeuds if n["groupe"] == "cycles" and n["id"] != "dashboard"}
    par_explo = {}
    for l in liens:
        if l["source"] in cycles and l["cible"].startswith("explorer."):
            par_explo.setdefault(l["cible"], set()).add(l["source"])
    multiples = {e: c for e, c in par_explo.items() if len(c) > 1}
    if not multiples:
        return None
    lanceurs = sorted(set().union(*multiples.values()))
    return _incoherence(
        "explorateurs_plusieurs_cycles", "Les explorateurs tournent dans plusieurs cycles",
        f"{len(multiples)} explorateur(s) lancé(s) par : {_noms(lanceurs)}.",
        list(multiples) + lanceurs)


def _tables_sans_ecrivain(noeuds, liens, arbres, comp):
    """Table lue en production dont les fonctions d'écriture ne sont appelées que dans un __main__."""
    trouves = []
    acces = ts.acces_tables(arbres, tc.TABLES)
    for table in tc.TABLES:
        ecrivains = {(c, f) for c, f, t, m, _, dm in acces
                     if t == table and m == "ecrit" and not dm and comp.get(c) not in (None, "outils")}
        if not ecrivains:
            continue
        appels = ts.appels_de(arbres, {f for _, f in ecrivains if f})
        prod = [a for f in appels for a in appels[f] if not a[2] and comp.get(a[0]) != "outils"]
        lecteurs = sorted({l["cible"] for l in liens if l["source"] == f"table:{table}"})
        if prod or not lecteurs:
            continue
        demo = [f"{c}:{l} (__main__)" for f in appels for c, l, dm in appels[f] if dm]
        # En aval : fichiers écrits par les MODULES lecteurs, puis composants qui lisent ces fichiers
        modules_lecteurs = {c for c, _, t, m, _, dm in acces if t == table and m == "lit" and not dm}
        fichiers = sorted({f"fichier:{nom}" for c, nom, mode, _ in
                           ts.acces_fichiers(arbres, set(tc.FICHIERS_MEMOIRE))
                           if c in modules_lecteurs and mode == "ecrit"})
        aval = sorted({l["cible"] for l in liens if l["source"] in fichiers} - set(lecteurs))
        suite = (f" En aval, via {', '.join(f[8:] for f in fichiers)} : {_noms(aval)}."
                 if aval else "")
        trouves.append(_incoherence(
            "table_sans_ecrivain_production", f"{table} n'est jamais écrite en production",
            f"Seules écritures : {', '.join(sorted(f'{c} ({f})' for c, f in ecrivains))}, appelées "
            f"uniquement depuis un bloc __main__ ou un outil manuel. Lue par : {_noms(lecteurs)}."
            + suite,
            [f"table:{table}"] + lecteurs + fichiers + aval + [comp[c] for c, _ in ecrivains if c in comp],
            demo))
    return trouves


def _par_tag(noeuds, tag, ident, titre):
    mods = [(n["id"], m["chemin"]) for n in noeuds for m in n["modules"] if tag in m["tags"]]
    if not mods:
        return None
    return _incoherence(ident, titre, f"{len(mods)} module(s) : "
                        + ", ".join(ts.nom_pointe(m) for _, m in mods) + ".", [c for c, _ in mods])


def detecter_incoherences(noeuds, liens, arbres, comp):
    """Liste des incohérences visibles sur la carte."""
    resultats = [_explorateurs_sans_prix(noeuds, liens)]
    resultats += _cycles_queue_sans_analyse(noeuds, liens)
    resultats.append(_explorateurs_plusieurs_cycles(noeuds, liens))
    resultats += _tables_sans_ecrivain(noeuds, liens, arbres, comp)
    resultats.append(_par_tag(noeuds, "orphelin", "modules_orphelins",
                              "Modules jamais atteints depuis un point d'entrée"))
    resultats.append(_par_tag(noeuds, "code-mort", "code_mort", "Code mort déclaré"))
    directs = [l for l in liens if l["type"] == "llm_direct"]
    if directs:
        resultats.append(_incoherence(
            "llm_hors_routeur", "Appels Gemini hors du routeur (hors réserve)",
            "Appels directs à ask_gemini, qui contournent GEMINI_RESERVE_POUR et le secours Groq.",
            [l["source"] for l in directs] + ["llm.gemini"], [p for l in directs for p in l["preuves"]]))
    return [r for r in resultats if r]
