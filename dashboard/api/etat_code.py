"""
dashboard/api/etat_code.py — Sources de l'état en direct, déduites du code (Phase 3, vue temps réel).

Rien n'est écrit à la main. Pour chaque composant de la carte :
- tables où il INSÈRE des lignes (requêtes littérales INSERT / REPLACE, sur toutes les tables
  créées par un CREATE TABLE du code) : l'horodatage de ces lignes date ses exécutions. UPDATE et
  DELETE ne comptent pas : une purge ne dit rien de l'activité du composant ;
- modules qui journalisent leur activité (logger.info / debug) : lignes dans logs/<tâche>.log ;
- tâches planifiées : nom de tâche de ses points d'entrée (utils.logger.nom_tache, comme les
  fichiers de logs), pour les composants du groupe « cycles » (cycles et dashboard).
Lecture seule : travaille sur les arbres AST déjà chargés par topology_build.
"""

import ast
import re

from dashboard.api import topology_composants as tc
from dashboard.api import topology_sources as ts

_CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?(\w+)", re.I)
_INSERE = re.compile(r"(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO)\s+[\"`\[]?(\w+)", re.I)


def _chaines(arbre):
    for noeud, fonction, dans_main in ts._parcourir(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            yield noeud, fonction, dans_main


def tables_declarees(arbres) -> set:
    """Tables créées par un CREATE TABLE littéral (hors tests et tables internes sqlite_*)."""
    return {m.group(1) for chemin, arbre in arbres.items() if not chemin.startswith("tests/")
            for n, _, _ in _chaines(arbre) for m in _CREATE.finditer(n.value)
            if not m.group(1).startswith("sqlite_")}


def insertions(arbres) -> list:
    """[(chemin, fonction, table, 'ecrit', ligne, dans_main)] : INSERT / REPLACE littéraux,
    au format de topology_sources.acces_tables (rattachés ensuite aux composants par _tables)."""
    tables = tables_declarees(arbres)
    trouves = set()
    for chemin, arbre in arbres.items():
        for n, fonction, dans_main in _chaines(arbre):
            for m in _INSERE.finditer(n.value):
                if m.group(1) in tables:
                    trouves.add((chemin, fonction, m.group(1), "ecrit", n.lineno, dans_main))
    return sorted(trouves, key=lambda x: (x[0], x[4], x[2]))


def journalisent(arbres) -> list:
    """Modules qui journalisent leur activité (logger.info / logger.debug) : un module qui n'écrit
    que ses avertissements et erreurs ne prouve pas, par son silence, qu'il n'a pas tourné."""
    return sorted(c for c, a in arbres.items() if any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("info", "debug")
        and isinstance(n.func.value, ast.Name) and "log" in n.func.value.id.lower() for n in ast.walk(a)))


def _points_d_entree(modules) -> list:
    """Scripts lancés directement : scripts/<x>.py (pas de sous-dossier), dashboard/app.py, main.py."""
    return [m for m in modules if (m.startswith("scripts/") and m.count("/") == 1)
            or m in ("dashboard/app.py", "main.py")]


def sources_etat(ecritures, arbres, comp) -> dict:
    """Ce que topology_etat lit en direct, par composant (dict sérialisable en JSON)."""
    from utils.logger import nom_tache

    par_comp = {}
    for m, c in comp.items():
        par_comp.setdefault(c, []).append(m)
    cycles = {c for c, (_, groupe, _) in tc.COMPOSANTS.items() if groupe == "cycles"}
    return {
        "tables_inserees": {c: sorted({l["cible"][6:] for l in ecritures.liens.values()
                                       if l["source"] == c and l["type"] == "ecrit"}) for c in tc.COMPOSANTS},
        "modules_journalises": journalisent(arbres),
        "taches": {c: sorted({nom_tache(m) for m in _points_d_entree(par_comp.get(c, []))})
                   for c in tc.COMPOSANTS if c in cycles},
    }
