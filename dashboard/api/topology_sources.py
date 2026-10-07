"""
dashboard/api/topology_sources.py — Lecture du code source pour la carte de l'agent (Phase 3).

Complète graph.json (Graphify) sur ce que l'AST des imports ne voit pas :
- imports dynamiques : chaîne littérale égale au nom pointé d'un module du projet
  (ex. `__import__("agents.explorers.crypto_explorer.explorer")` du tactical) ;
- accès aux tables SQLite : requêtes littérales (INSERT/UPDATE/DELETE = écrit,
  FROM/JOIN = lit), rattachées à la fonction qui les contient ;
- appels LLM : ask_llm / ask_gemini / ask_gemini_status et leur `appelant` ;
- réserve Gemini : valeur par défaut de GEMINI_RESERVE_POUR dans config.py ;
- appels de fonctions hors des blocs `if __name__ == "__main__"`.
Lecture seule : aucun module du projet n'est importé.
"""

import os
import re
import ast

FONCTIONS_LLM = {"ask_llm": "routeur", "ask_gemini": "gemini", "ask_gemini_status": "gemini"}
_ECRIT = r"(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)\s+{t}\b"
_LIT = r"(?:FROM|JOIN)\s+{t}\b"


def nom_pointe(chemin):
    """agents/skills/__init__.py -> agents.skills ; config.py -> config."""
    sans_ext = chemin[:-3] if chemin.endswith(".py") else chemin
    if sans_ext.endswith("/__init__"):
        sans_ext = sans_ext[: -len("/__init__")]
    return sans_ext.replace("/", ".")


def _est_bloc_main(noeud):
    """Vrai pour `if __name__ == "__main__":`."""
    if not isinstance(noeud, ast.If) or not isinstance(noeud.test, ast.Compare):
        return False
    t = noeud.test
    return (isinstance(t.left, ast.Name) and t.left.id == "__name__"
            and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in t.comparators))


def _parcourir(arbre):
    """Itère (nœud, fonction englobante ou None, dans_main) sur tout l'arbre."""
    pile = [(arbre, None, False)]
    while pile:
        noeud, fonction, dans_main = pile.pop()
        yield noeud, fonction, dans_main
        for enfant in ast.iter_child_nodes(noeud):
            f = enfant.name if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef)) else fonction
            pile.append((enfant, f, dans_main or _est_bloc_main(noeud)))


def charger_arbres(racine, modules):
    """{chemin: arbre AST} des modules lisibles (les autres sont ignorés)."""
    arbres = {}
    for chemin in modules:
        try:
            with open(os.path.join(racine, chemin), encoding="utf-8") as f:
                arbres[chemin] = ast.parse(f.read())
        except (OSError, SyntaxError, ValueError):
            continue
    return arbres


def imports_dynamiques(arbres):
    """[(importeur, importé, ligne)] : chaînes égales au nom pointé d'un autre module."""
    par_nom = {nom_pointe(c): c for c in arbres if "." in nom_pointe(c)}
    trouves = []
    for chemin, arbre in arbres.items():
        for noeud, _, _ in _parcourir(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                cible = par_nom.get(noeud.value)
                if cible and cible != chemin:
                    trouves.append((chemin, cible, noeud.lineno))
    return trouves


def acces_tables(arbres, tables):
    """[(chemin, fonction, table, 'lit'|'ecrit', ligne, dans_main)] depuis les requêtes littérales."""
    motifs = {t: (re.compile(_ECRIT.format(t=t), re.I), re.compile(_LIT.format(t=t))) for t in tables}
    trouves = set()
    for chemin, arbre in arbres.items():
        for noeud, fonction, dans_main in _parcourir(arbre):
            if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)):
                continue
            for table, (ecrit, lit) in motifs.items():
                if ecrit.search(noeud.value):
                    trouves.add((chemin, fonction, table, "ecrit", noeud.lineno, dans_main))
                if lit.search(noeud.value):
                    trouves.add((chemin, fonction, table, "lit", noeud.lineno, dans_main))
    return sorted(trouves, key=lambda x: (x[0], x[4], x[2], x[3]))


def _ecrit_des_fichiers(arbre):
    """Heuristique : le module ouvre un fichier en 'w'/'a' ou appelle .write / .write_text."""
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        nom = _nom_appele(noeud)
        if nom in ("write", "write_text", "writelines"):
            return True
        if nom == "open":
            modes = [a for a in noeud.args[1:2]] + [k.value for k in noeud.keywords if k.arg == "mode"]
            if any(isinstance(m, ast.Constant) and isinstance(m.value, str)
                   and ("w" in m.value or "a" in m.value) for m in modes):
                return True
    return False


def acces_fichiers(arbres, noms):
    """[(chemin, fichier, 'lit'|'ecrit', ligne)] : modules qui citent un fichier de mémoire."""
    trouves = []
    for chemin, arbre in arbres.items():
        mode = "ecrit" if _ecrit_des_fichiers(arbre) else "lit"
        for noeud, _, dans_main in _parcourir(arbre):
            if isinstance(noeud, ast.Constant) and noeud.value in noms and not dans_main:
                trouves.append((chemin, noeud.value, mode, noeud.lineno))
    return trouves


def _nom_appele(appel):
    f = appel.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def appels_llm(arbres):
    """[(chemin, fonction_llm, appelant, ligne, dans_main)] hors des modules LLM eux-mêmes."""
    trouves = []
    for chemin, arbre in arbres.items():
        if chemin in ("utils/llm.py", "utils/gemini.py"):
            continue
        for noeud, _, dans_main in _parcourir(arbre):
            if isinstance(noeud, ast.Call) and _nom_appele(noeud) in FONCTIONS_LLM:
                appelant = next((k.value.value for k in noeud.keywords
                                 if k.arg == "appelant" and isinstance(k.value, ast.Constant)), None)
                trouves.append((chemin, _nom_appele(noeud), appelant, noeud.lineno, dans_main))
    return sorted(trouves, key=lambda x: (x[0], x[3]))


def appels_de(arbres, noms):
    """{nom: [(chemin, ligne, dans_main)]} : appels des fonctions nommées, partout."""
    trouves = {n: [] for n in noms}
    for chemin, arbre in arbres.items():
        for noeud, _, dans_main in _parcourir(arbre):
            if isinstance(noeud, ast.Call) and _nom_appele(noeud) in trouves:
                trouves[_nom_appele(noeud)].append((chemin, noeud.lineno, dans_main))
    return trouves


def reserve_gemini_defaut(racine):
    """Appelants réservés à Gemini : défaut de GEMINI_RESERVE_POUR lu dans config.py."""
    try:
        with open(os.path.join(racine, "config.py"), encoding="utf-8") as f:
            arbre = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "GEMINI_RESERVE_POUR" for c in noeud.targets):
            for c in ast.walk(noeud.value):
                if isinstance(c, ast.Constant) and isinstance(c.value, str) \
                        and c.value not in ("GEMINI_RESERVE_POUR", ","):
                    return sorted(a.strip().lower() for a in c.value.split(",") if a.strip())
    return None


def commit_head(racine):
    """SHA du commit courant, lu dans .git sans lancer git (None si introuvable)."""
    git = os.path.join(racine, ".git")
    try:
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            tete = f.read().strip()
        if not tete.startswith("ref: "):
            return tete
        ref = tete[5:]
        chemin_ref = os.path.join(git, *ref.split("/"))
        if os.path.exists(chemin_ref):
            with open(chemin_ref, encoding="utf-8") as f:
                return f.read().strip()
        with open(os.path.join(git, "packed-refs"), encoding="utf-8") as f:
            for ligne in f:
                if ligne.strip().endswith(" " + ref):
                    return ligne.split()[0]
    except OSError:
        pass
    return None
