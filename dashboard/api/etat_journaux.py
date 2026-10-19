"""
dashboard/api/etat_journaux.py — Activité lue dans logs/<tâche>.log et logs/<tâche>_errors.log
(vue temps réel de la carte, Phase 3).

LECTURE SEULE. Format des lignes (utils/logger.py) : « AAAA-MM-JJ HH:MM:SS | NIVEAU | logger | message »,
à l'heure locale de la machine. Les heures restent des chaînes de ce format : comparées telles quelles.
- Un passage commence à une ligne contenant « démarrage » écrite par le logger d'entrée de la tâche
  (cycle_<tâche>, __main__ ou le nom du script) ; les lignes d'avant le premier démarrage du
  fichier forment un passage commencé à la première ligne.
- Pour chaque logger : heure de sa dernière ligne et passages où il a écrit ; dans <tâche>_errors.log,
  sa dernière ligne ERROR ou CRITICAL (heure et message).
- logs/<tâche>.log.1 (rotation) est lu aussi quand le fichier courant commence il y a moins de 24 h.
Chaque fichier n'est relu que s'il a changé (taille, date) ; seule sa fin (TAILLE_MAX) est lue.
"""

import os
import threading

TAILLE_MAX = 8 * 1024 * 1024
NIVEAUX_ERREUR = ("ERROR", "CRITICAL")

_cache = {}
_verrou = threading.Lock()


def _lignes(chemin):
    """Lignes de la fin du fichier (la première, coupée, est écartée si le fichier est tronqué)."""
    with open(chemin, "rb") as f:
        f.seek(0, os.SEEK_END)
        taille = f.tell()
        f.seek(max(0, taille - TAILLE_MAX))
        brut = f.read()
    lignes = brut.decode("utf-8", errors="replace").splitlines()
    return lignes[1:] if taille > TAILLE_MAX else lignes


def _decouper(ligne):
    morceaux = ligne.split(" | ", 3)
    if len(morceaux) < 4 or len(morceaux[0]) != 19 or morceaux[0][4] != "-":
        return None  # suite d'une trace (traceback) ou ligne étrangère au format
    return morceaux[0], morceaux[1].strip(), morceaux[2].strip(), morceaux[3]


def _analyser(chemins_log, chemin_erreurs, entrees):
    passages, par_logger, erreurs, premiere = [], {}, {}, None
    for chemin in chemins_log:
        for ligne in _lignes(chemin):
            p = _decouper(ligne)
            if p is None:
                continue
            heure, _, nom, message = p
            premiere = premiere or heure
            if (nom in entrees and "démarrage" in message) or not passages:
                passages.append(heure)
            info = par_logger.setdefault(nom, {"derniere": heure, "passages": set()})
            info["derniere"] = max(info["derniere"], heure)
            info["passages"].add(len(passages) - 1)
    if chemin_erreurs:
        for ligne in _lignes(chemin_erreurs):
            p = _decouper(ligne)
            if p and p[1] in NIVEAUX_ERREUR and p[0] >= erreurs.get(p[2], ("",))[0]:
                erreurs[p[2]] = (p[0], p[3][:300])
    return {"passages": passages, "par_logger": par_logger, "erreurs": erreurs, "premiere": premiere}


def _empreinte(chemins):
    return tuple((c, os.path.getsize(c), os.path.getmtime(c)) for c in chemins if os.path.exists(c))


def lire_journal(dossier, tache, depuis):
    """Résumé de la tâche (None sans logs/<tâche>.log). depuis : heure locale « AAAA-MM-JJ HH:MM:SS »
    du début de la fenêtre ; décide seulement s'il faut lire aussi la sauvegarde .1."""
    courant = os.path.join(dossier, f"{tache}.log")
    if not os.path.exists(courant):
        return None
    erreurs = os.path.join(dossier, f"{tache}_errors.log")
    chemins = [courant]
    sauvegarde = courant + ".1"
    if os.path.exists(sauvegarde):
        with open(courant, "rb") as f:
            debut = f.read(8192).decode("utf-8", errors="replace").splitlines()
        tete = next((p for p in map(_decouper, debut) if p), None)
        if tete is None or tete[0] > depuis:
            chemins.insert(0, sauvegarde)
    cle = _empreinte(chemins + [erreurs])
    with _verrou:
        if _cache.get(tache, (None,))[0] == cle:
            return _cache[tache][1]
    entrees = {f"cycle_{tache}", "__main__", tache}
    resume = _analyser(chemins, erreurs if os.path.exists(erreurs) else None, entrees)
    resume["fichier"] = f"{tache}.log"
    with _verrou:
        _cache[tache] = (cle, resume)
    return resume


def taches_journalisees(dossier):
    """Tâches qui ont la paire <tâche>.log + <tâche>_errors.log de utils/logger.py. Écarte les
    sorties brutes du planificateur (task_*.log, parfois de plusieurs Go) et les anciens journaux
    communs, qui n'ont pas de fichier _errors jumeau."""
    try:
        noms = set(os.listdir(dossier))
    except OSError:
        return []
    return sorted(n[:-4] for n in noms if n.endswith(".log") and not n.endswith("_errors.log")
                  and f"{n[:-4]}_errors.log" in noms)


def lire_journaux(dossier, depuis):
    """{tâche: résumé} pour chaque tâche journalisée du dossier."""
    sortie = {}
    for t in taches_journalisees(dossier):
        r = lire_journal(dossier, t, depuis)
        if r is not None:
            sortie[t] = r
    return sortie
