"""
dashboard/api/topology_build.py — Assemble la carte de l'agent (Phase 3), lecture seule.

Sources : graphify-out/graph.json (imports, appels entre fonctions) + lecture
du code (topology_sources) + table écrite à la main (topology_composants).
Les modules sont regroupés en composants ; un lien porte ses preuves
(fichier:ligne). Chaque nœud a un champ `etat` (None ici) : emplacement de
l'état en direct lu dans le registre, branché sur la tour.
"""

import os
import json
from collections import defaultdict
from datetime import datetime, timezone

from dashboard.api import topology_composants as tc
from dashboard.api import topology_sources as ts
from dashboard.api.topology_incoherences import detecter_incoherences

MAX_PREUVES = 6
PROFONDEUR_APPELS = 4  # remontée des appelants à travers l'infrastructure masquée


def _fichier(noeud):
    return (noeud.get("source_file") or "").replace("\\", "/")


class _Carte:
    """Accumule nœuds et liens au niveau composant."""

    def __init__(self):
        self.liens = {}

    def lier(self, source, cible, type_lien, preuve, **attributs):
        if source == cible or source in tc.MASQUES or cible in tc.MASQUES:
            return
        cle = (source, cible, type_lien, tuple(sorted(attributs.items())))
        lien = self.liens.setdefault(cle, {"source": source, "cible": cible, "type": type_lien,
                                           "preuves": [], "nombre": 0, **attributs})
        lien["nombre"] += 1
        if preuve not in lien["preuves"] and len(lien["preuves"]) < MAX_PREUVES:
            lien["preuves"].append(preuve)


def _imports(graphe, noeuds, comp, carte):
    """Arêtes imports / imports_from de graph.json -> deps de modules + liens 'import'."""
    deps = defaultdict(set)
    for e in graphe["links"]:
        if e.get("relation") not in ("imports", "imports_from"):
            continue
        a = (e.get("source_file") or "").replace("\\", "/")
        bouts = {_fichier(noeuds.get(e["source"], {})), _fichier(noeuds.get(e["target"], {}))}
        b = next((f for f in bouts if f and f != a), None)
        if a in comp and b in comp:
            deps[a].add(b)
            carte.lier(comp[a], comp[b], "import", f"{a}:{(e.get('source_location') or 'L?')[1:]}")
    return deps


def _appelants(graphe, noeuds):
    """{id fonction appelée: [(id appelant, ligne)]} depuis les arêtes 'calls'."""
    appelants = defaultdict(list)
    for e in graphe["links"]:
        if e.get("relation") == "calls":
            appelants[e["target"]].append((e["source"], (e.get("source_location") or "L?")[1:]))
    return appelants


def _tables(arbres, graphe, noeuds, comp, carte):
    """Liens 'ecrit' (composant -> table) et 'lit' (table -> composant)."""
    index = {(_fichier(n), n["label"].lstrip(".")): i for i, n in noeuds.items()}
    appelants = _appelants(graphe, noeuds)
    for chemin, fonction, table, mode, ligne, dans_main in ts.acces_tables(arbres, tc.TABLES):
        if dans_main or comp.get(chemin) in (None, "outils"):
            continue  # démonstration ou outil manuel : pas un flux de production
        cible = f"table:{table}"
        a_voir = [(chemin, fonction, f"{chemin}:{ligne}", 0)]
        while a_voir:
            fichier, fct, preuve, profondeur = a_voir.pop()
            c = comp.get(fichier)
            if c not in tc.MASQUES:
                if mode == "ecrit":
                    carte.lier(c, cible, "ecrit", preuve)
                else:
                    carte.lier(cible, c, "lit", preuve)
                continue
            if c != "infra" or profondeur >= PROFONDEUR_APPELS or fct is None:
                continue
            for appelant, l in appelants.get(index.get((fichier, f"{fct}()")), []):
                n = noeuds.get(appelant, {})
                a_voir.append((_fichier(n), n.get("label", "").strip(".()"),
                               f"{_fichier(n)}:{l} ({n.get('label', '').strip('.')})", profondeur + 1))


def _llm(arbres, comp, carte, reserve):
    """Liens vers Gemini / Groq selon la fonction appelée et l'appelant."""
    for chemin, fonction, appelant, ligne, dans_main in ts.appels_llm(arbres):
        c, preuve = comp.get(chemin), f"{chemin}:{ligne}"
        if c is None:
            continue
        if ts.FONCTIONS_LLM[fonction] == "gemini":
            carte.lier(c, "llm.gemini", "llm_direct", preuve, appelant="(hors routeur)")
            continue
        nom = appelant or "(sans appelant)"
        if reserve is None or appelant is None or appelant.lower() in reserve:
            carte.lier(c, "llm.gemini", "llm", preuve, appelant=nom)
            carte.lier(c, "llm.groq", "llm", preuve, appelant=nom, role="secours")
        else:
            carte.lier(c, "llm.groq", "llm", preuve, appelant=nom, role="direct")


def construire_topologie(racine, chemin_graphe):
    """Carte complète (dict sérialisable en JSON). Lève FileNotFoundError sans graph.json."""
    from scripts.graphify_modules import CODE_MORT, modules_atteints

    with open(chemin_graphe, encoding="utf-8") as f:
        graphe = json.load(f)
    noeuds = {n["id"]: n for n in graphe["nodes"]}
    modules = sorted({_fichier(n) for n in noeuds.values() if _fichier(n).endswith(".py")})
    comp = {m: tc.composant(m) for m in modules}
    non_classes = [m for m, c in comp.items() if c is None]
    comp = {m: c for m, c in comp.items() if c is not None}

    carte = _Carte()
    deps = _imports(graphe, noeuds, comp, carte)
    arbres = ts.charger_arbres(racine, modules)
    for a, b, ligne in ts.imports_dynamiques(arbres):
        if a in comp and b in comp:
            deps[a].add(b)
            carte.lier(comp[a], comp[b], "import_dynamique", f"{a}:{ligne}")
    _tables(arbres, graphe, noeuds, comp, carte)
    for chemin, nom, mode, ligne in ts.acces_fichiers(arbres, set(tc.FICHIERS_MEMOIRE)):
        if comp.get(chemin) not in (None, "outils"):
            source, cible = (comp[chemin], f"fichier:{nom}") if mode == "ecrit" else (f"fichier:{nom}", comp[chemin])
            carte.lier(source, cible, mode, f"{chemin}:{ligne}")
    reserve = ts.reserve_gemini_defaut(racine)
    _llm(arbres, comp, carte, reserve)

    atteints = modules_atteints(set(modules), deps)
    tags_module = {m: ["code-mort"] if m in CODE_MORT else [] if m in atteints else ["orphelin"]
                   for m in comp}
    par_comp = defaultdict(list)
    for m, c in comp.items():
        par_comp[c].append({"chemin": m, "tags": tags_module[m]})

    sortie = []
    for cid, (libelle, groupe, frequence) in tc.COMPOSANTS.items():
        mods = sorted(par_comp.get(cid, []), key=lambda x: x["chemin"])
        tags = sorted({t for m in mods for t in m["tags"]}) if mods and all(m["tags"] for m in mods) else []
        sortie.append({"id": cid, "libelle": libelle, "groupe": groupe, "type": "composant",
                       "frequence": frequence, "modules": mods, "tags": tags,
                       "annotation": tc.ANNOTATIONS.get(cid), "etat": None})
    donnees = [("table", t) for t in tc.TABLES] + [("fichier", f) for f in tc.FICHIERS_MEMOIRE]
    for genre, nom in donnees:
        sortie.append({"id": f"{genre}:{nom}", "libelle": nom, "groupe": "ressources", "type": genre,
                       "frequence": None, "modules": [], "tags": [],
                       "annotation": tc.ANNOTATIONS.get(f"{genre}:{nom}"), "etat": None})

    liens = sorted(carte.liens.values(), key=lambda l: (l["source"], l["cible"], l["type"]))
    commit_graphe, head = graphe.get("built_at_commit"), ts.commit_head(racine)
    return {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graphe": {"commit": commit_graphe, "head": head,
                   "a_jour": bool(commit_graphe and head and commit_graphe == head),
                   "graphify": (graphe.get("graph") or {}).get("graphify_version")},
        "reserve_gemini": {"appelants": reserve, "source": "config.py (valeur par défaut)"},
        "groupes": [{"id": g, "libelle": l} for g, l in tc.GROUPES],
        "noeuds": sortie,
        "liens": liens,
        "incoherences": detecter_incoherences(sortie, liens, arbres, comp),
        "non_classes": non_classes,
        "etat_source": None,  # registre de la tour : branché plus tard
    }
