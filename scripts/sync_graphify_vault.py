"""
scripts/sync_graphify_vault.py — Copie la carte du code Graphify dans le vault Obsidian.

Copie (pas de jonction) : le vault ne pointe jamais vers le dépôt, donc une
suppression dans Obsidian ne touche pas graphify-out/, et le cache d'extraction
(milliers de JSON) n'est pas indexé. À relancer après chaque régénération :
  graphify extract . --code-only
  graphify cluster-only . --no-label

Fichiers copiés : GRAPH_REPORT.md (lisible dans Obsidian) et graph.html
(graphe interactif, à ouvrir dans un navigateur).

Usage :
  python scripts/sync_graphify_vault.py                       # vault par défaut
  python scripts/sync_graphify_vault.py --vault D:\\MonVault
  python scripts/sync_graphify_vault.py --dry-run             # affiche sans copier
Code de sortie : 0 si tout est copié, 1 si un fichier source manque.
"""

import os
import sys
import shutil
import argparse

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(RACINE, "graphify-out")
VAULT_DEFAUT = os.path.join(os.path.expanduser("~"), "Documents", "AlphaSignalVault")
DOSSIER_VAULT = "90-Graphify"
FICHIERS = ("GRAPH_REPORT.md", "graph.html")


def sync_vault(source, vault, dry_run=False):
    """Copie les FICHIERS de source vers vault/90-Graphify ; renvoie la liste des manquants."""
    cible = os.path.join(vault, DOSSIER_VAULT)
    manquants = [f for f in FICHIERS if not os.path.isfile(os.path.join(source, f))]
    if manquants:
        return manquants
    if not dry_run:
        os.makedirs(cible, exist_ok=True)
    for nom in FICHIERS:
        src = os.path.join(source, nom)
        dst = os.path.join(cible, nom)
        print(f"{'[dry-run] ' if dry_run else ''}{src} -> {dst}")
        if not dry_run:
            # copy2 conserve la date de modification (utile pour voir la fraîcheur)
            shutil.copy2(src, dst)
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--vault", default=VAULT_DEFAUT, help="dossier racine du vault Obsidian")
    parser.add_argument("--source", default=SOURCE, help="dossier de sortie Graphify")
    parser.add_argument("--dry-run", action="store_true", help="affiche les copies sans les faire")
    args = parser.parse_args()

    try:
        manquants = sync_vault(args.source, args.vault, args.dry_run)
    except OSError as exc:
        print(f"Erreur de copie : {exc}", file=sys.stderr)
        return 1
    if manquants:
        print(f"Fichiers absents de {args.source} : {', '.join(manquants)}", file=sys.stderr)
        print("Lancer d'abord : graphify extract . --code-only puis "
              "graphify cluster-only . --no-label", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
