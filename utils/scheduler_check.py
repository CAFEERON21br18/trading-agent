"""
utils/scheduler_check.py — Vérification des tâches planifiées Windows.
Logique commune à scripts/check_status.py et scripts/check_health.py
(le côté macOS/launchd reste propre à chaque script, inchangé).

Les 7 tâches sont créées par scripts/install_tasks_windows.ps1 dans le
dossier \\AlphaSignal\\ du Planificateur de tâches Windows.
"""

import csv
import io
import subprocess

DOSSIER_TACHES_WINDOWS = "\\AlphaSignal\\"
TACHES_WINDOWS = ["critical", "tactical", "strategic", "daily", "weekly", "cleanup", "dashboard"]

# Codes LastTaskResult (schtasks) à connaître — tout code hors de cette liste = échec.
CODE_SUCCES        = 0
CODE_EN_COURS      = 267009  # normal pour "dashboard" (tâche continue au démarrage)
CODE_JAMAIS_LANCEE = 267011  # normal pour "weekly"/"cleanup" avant leur premier passage

# Tâches pour lesquelles "jamais lancée" est un état attendu (pas encore de dimanche écoulé).
TACHES_JAMAIS_LANCEE_OK = {"weekly", "cleanup"}


def verifier_taches_windows(noms: list[str] | None = None,
                             dossier: str = DOSSIER_TACHES_WINDOWS) -> tuple[bool, list[str], list[str], list[str]]:
    """
    Interroge le Planificateur de tâches Windows (schtasks) pour chaque tâche
    AlphaSignal attendue.

    Retourne (ok, details, manquantes, echecs) :
      - ok         : True si les 7 tâches existent et sont saines
      - details    : une ligne lisible par tâche
      - manquantes : noms des tâches absentes du Planificateur
      - echecs     : noms des tâches présentes mais avec un LastTaskResult inattendu
    """
    noms = noms if noms is not None else TACHES_WINDOWS
    details: list[str] = []
    manquantes: list[str] = []
    echecs: list[str] = []

    for nom in noms:
        chemin_tache = f"{dossier}{nom}"
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", chemin_tache, "/FO", "CSV", "/V"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            echecs.append(nom)
            details.append(f"{nom} : erreur d'appel à schtasks ({e})")
            continue

        if result.returncode != 0:
            manquantes.append(nom)
            details.append(f"{nom} : tâche absente du Planificateur")
            continue

        code = _dernier_resultat(result.stdout)
        if code is None:
            echecs.append(nom)
            details.append(f"{nom} : dernier résultat illisible dans la sortie schtasks")
            continue

        if code == CODE_SUCCES:
            details.append(f"{nom} : OK (dernier résultat 0)")
        elif code == CODE_EN_COURS:
            details.append(f"{nom} : en cours d'exécution (normal)")
        elif code == CODE_JAMAIS_LANCEE and nom in TACHES_JAMAIS_LANCEE_OK:
            details.append(f"{nom} : jamais lancée — normal avant son premier passage")
        elif code == CODE_JAMAIS_LANCEE:
            echecs.append(nom)
            details.append(f"{nom} : jamais lancée (code {code}) — inattendu pour cette tâche")
        else:
            echecs.append(nom)
            details.append(f"{nom} : échec (dernier résultat {code})")

    ok = not manquantes and not echecs
    return ok, details, manquantes, echecs


def _dernier_resultat(sortie_csv: str) -> int | None:
    """Extrait la colonne 'Last Result' d'une sortie `schtasks /FO CSV /V`."""
    lecteur = csv.DictReader(io.StringIO(sortie_csv))
    ligne = next(lecteur, None)
    if not ligne:
        return None
    valeur = ligne.get("Last Result")
    if valeur is None:
        return None
    try:
        return int(valeur.strip())
    except ValueError:
        return None
