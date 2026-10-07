"""
scripts/graphify_modules.py — Notes Obsidian « une note par module » depuis graphify-out/graph.json.

Utilisé par scripts/sync_graphify_vault.py (dossier 90-Graphify/modules/ du vault).
- Nom de note en notation pointée : agents/decision_engine.py -> agents.decision_engine,
  agents/skills/__init__.py -> agents.skills.
- Liens [[...]] uniquement vers les modules importés : les flèches de la vue graphe
  d'Obsidian montrent le vrai sens des dépendances. « Importé par » en texte simple.
- Tags (frontmatter, pour colorer la vue graphe) :
  code-mort : liste déclarée CODE_MORT (docs/TODO.md §10) ;
  orphelin  : module jamais atteint depuis un point d'entrée (scripts/, main.py,
              dashboard/app.py) en suivant les imports ; calculé à chaque passage.
Seules les arêtes AST `imports` / `imports_from` sont retenues (aucune arête inférée).
"""

import os
import ast
import json
from collections import defaultdict

MARQUEUR = "genere_par: sync_graphify_vault"
RELATIONS_IMPORT = ("imports", "imports_from")
POINTS_ENTREE = ("main.py", "dashboard/app.py")

# Code mort confirmé (docs/TODO.md §10) : chargé ou non, jamais appelé
CODE_MORT = {
    "agents/skills/pipeline.py",
    "agents/skills/bayesien.py",
    "agents/skills/base_rates.py",
    "agents/skills/metacognition.py",
    "agents/skills/pre_mortem.py",
    "agents/skills/second_ordre.py",
    "agents/backtester/visualizer.py",
}


def nom_module(chemin):
    """agents/skills/__init__.py -> agents.skills ; config.py -> config."""
    sans_ext = chemin[:-3] if chemin.endswith(".py") else chemin
    if sans_ext.endswith("/__init__"):
        sans_ext = sans_ext[: -len("/__init__")]
    return sans_ext.replace("/", ".")


def charger_dependances(chemin_graphe):
    """Renvoie (modules, deps) : fichiers .py du graphe et {importeur: {importés}}."""
    with open(chemin_graphe, encoding="utf-8") as f:
        graphe = json.load(f)
    fichier = {n["id"]: (n.get("source_file") or "").replace("\\", "/") for n in graphe["nodes"]}
    modules = {f for f in fichier.values() if f.endswith(".py")}
    deps = defaultdict(set)
    for arete in graphe.get("links", graphe.get("edges", [])):
        a, b = fichier.get(arete["source"], ""), fichier.get(arete["target"], "")
        if a in modules and b in modules and a != b and arete.get("relation") in RELATIONS_IMPORT:
            deps[a].add(b)
    return modules, deps


def _inits_parents(chemin, modules):
    """__init__.py des paquets englobants : Python les exécute à l'import du module."""
    parties = chemin.split("/")[:-1]
    for i in range(1, len(parties) + 1):
        init = "/".join(parties[:i]) + "/__init__.py"
        if init in modules:
            yield init


def modules_atteints(modules, deps):
    """Modules atteints depuis les points d'entrée en suivant les imports."""
    a_voir = [m for m in modules if m.startswith("scripts/") or m in POINTS_ENTREE]
    vus = set()
    while a_voir:
        m = a_voir.pop()
        if m in vus:
            continue
        vus.add(m)
        a_voir.extend(deps[m])
        a_voir.extend(_inits_parents(m, modules))
    return vus


def _description(racine, chemin):
    """Première ligne de la docstring du module, ou chaîne vide."""
    try:
        with open(os.path.join(racine, chemin), encoding="utf-8") as f:
            doc = ast.get_docstring(ast.parse(f.read())) or ""
    except (OSError, SyntaxError, ValueError):
        return ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def generer_notes(chemin_graphe, racine):
    """Renvoie {nom_note: contenu_markdown} pour tous les modules .py du graphe."""
    modules, deps = charger_dependances(chemin_graphe)
    atteints = modules_atteints(modules, deps)
    importe_par = defaultdict(set)
    for a, cibles in deps.items():
        for b in cibles:
            importe_par[b].add(a)

    notes = {}
    for m in sorted(modules):
        tags = ["code-mort"] if m in CODE_MORT else ["orphelin"] if m not in atteints else []
        lignes = ["---", f"module: {nom_module(m)}", f'fichier: "{m}"', MARQUEUR]
        lignes += ["tags:"] + [f"  - {t}" for t in tags] if tags else []
        lignes += ["---", "", f"# {nom_module(m)}", "", f"`{m}`"]
        desc = _description(racine, m)
        if desc:
            lignes += ["", f"> {desc}"]
        lignes += ["", "## Importe", ""]
        lignes += [f"- [[{nom_module(b)}]]" for b in sorted(deps[m], key=nom_module)] or ["_aucun module du projet_"]
        lignes += ["", "## Importé par", ""]
        lignes += [f"- {nom_module(a)}" for a in sorted(importe_par[m], key=nom_module)] or ["_aucun_"]
        notes[nom_module(m)] = "\n".join(lignes) + "\n"
    return notes


def ecrire_notes(dossier, notes, dry_run=False):
    """Écrit les notes et retire celles générées lors d'un passage précédent et disparues.

    Une note sans le MARQUEUR (écrite à la main) n'est jamais modifiée ni supprimée.
    Renvoie (écrites, supprimées, ignorées).
    """
    ecrites, supprimees, ignorees = 0, 0, []
    existantes = os.listdir(dossier) if os.path.isdir(dossier) else []
    if not dry_run:
        os.makedirs(dossier, exist_ok=True)
    for nom, contenu in notes.items():
        chemin = os.path.join(dossier, nom + ".md")
        if os.path.exists(chemin) and not _est_generee(chemin):
            ignorees.append(nom)
            continue
        if not dry_run:
            with open(chemin, "w", encoding="utf-8", newline="\n") as f:
                f.write(contenu)
        ecrites += 1
    for fichier in existantes:
        chemin = os.path.join(dossier, fichier)
        if fichier.endswith(".md") and fichier[:-3] not in notes and _est_generee(chemin):
            if not dry_run:
                os.remove(chemin)
            supprimees += 1
    return ecrites, supprimees, ignorees


def _est_generee(chemin):
    """Vrai si la note porte le MARQUEUR de ce script dans son frontmatter."""
    try:
        with open(chemin, encoding="utf-8") as f:
            return MARQUEUR in f.read(500)
    except OSError:
        return False
