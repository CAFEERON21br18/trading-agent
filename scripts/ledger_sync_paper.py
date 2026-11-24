"""
scripts/ledger_sync_paper.py — Positions paper de l'agent vers le grand livre (data/ledger.db).

Outil manuel : aucune tâche planifiée ne le lance, aucun cycle ne l'importe. La base de l'agent
(data/database.db) est ouverte en lecture seule ; seule la table positions est lue.
- Une position fermée donne deux exécutions (entrée, sortie), une position ouverte une seule,
  sur le compte « Paper agent » (type paper). Relancer le script n'ajoute aucun doublon.
- Positions « boucle » : jamais importées. Sans la colonne de marquage, le script s'arrête sans
  rien importer (lancer d'abord scripts/marquer_boucles.py --appliquer). Une position importée
  puis marquée « boucle » est annulée par une ligne d'annulation, jamais supprimée.
- Devise de cotation : EUR pour les suffixes .PA .DE .AS .MI .MC .LS, USD sinon. Les tickers
  dont la devise reste incertaine sont listés à la fin.
- Aucun coût inscrit : le paper trader ne compte pas de frais (résultats bruts de frais).

À BLANC PAR DÉFAUT : rien n'est écrit, le script affiche ce qu'il ferait ; si le grand livre
n'existe pas encore, il n'est pas créé. Avec --appliquer : écriture, tout ou rien.

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\ledger_sync_paper.py              (à blanc)
    .venv\\Scripts\\python.exe scripts\\ledger_sync_paper.py --appliquer  (écrit)
"""

import argparse
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import ledger  # noqa: E402
from importeurs import paper  # noqa: E402

BASE_DEFAUT = os.path.join(RACINE, "data", "database.db")
LEDGER_DEFAUT = os.path.join(RACINE, "data", "ledger.db")


def lancer(base: str = BASE_DEFAUT, grand_livre: str = LEDGER_DEFAUT, appliquer: bool = False) -> int:
    """Synchronise et affiche le rapport. Code de sortie : 0, ou 1 si rien n'a pu être importé."""
    try:
        paper.lire_positions(base)  # base lisible et colonne « boucle » présente, avant d'ouvrir le grand livre
    except paper.SynchronisationImpossible as exc:
        print(f"ERREUR : {exc}")
        return 1
    # À blanc et sans grand livre existant : base en mémoire, aucun fichier créé
    chemin = grand_livre if appliquer or os.path.exists(grand_livre) else ":memory:"
    conn = ledger.ouvrir(chemin)
    try:
        rapport = paper.synchroniser(conn, base, appliquer=appliquer)
    finally:
        conn.close()
    if rapport.erreurs:
        print(f"ERREUR : {len(rapport.erreurs)} position(s) illisible(s), rien n'a été écrit.")
        for pos_id, raison in rapport.erreurs:
            print(f"  position #{pos_id} : {raison}")
        return 1
    print("Synchronisation appliquée." if appliquer else "À BLANC : rien n'a été écrit (--appliquer pour écrire).")
    print(f"  positions lues hors boucle      : {rapport.positions}")
    print(f"  positions boucle, non importées : {rapport.boucles}")
    print(f"  exécutions ajoutées             : {rapport.importes}")
    print(f"  exécutions déjà présentes       : {rapport.deja_presents}")
    print(f"  exécutions annulées (boucle)    : {rapport.annules}")
    if rapport.devises_incertaines:
        print("  devise incertaine, enregistrée en USD par défaut : " + ", ".join(rapport.devises_incertaines))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Positions paper vers le grand livre (à blanc par défaut).")
    p.add_argument("--appliquer", action="store_true", help="écrire dans le grand livre ; sinon à blanc")
    p.add_argument("--base", default=BASE_DEFAUT, help="base de l'agent, lue en lecture seule")
    p.add_argument("--ledger", default=LEDGER_DEFAUT, help="grand livre")
    args = p.parse_args(argv)
    return lancer(args.base, args.ledger, args.appliquer)


if __name__ == "__main__":
    sys.exit(main())
