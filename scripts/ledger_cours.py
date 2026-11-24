"""
scripts/ledger_cours.py — Clôtures quotidiennes des instruments du grand livre vers la table cours.

Outil manuel : aucune tâche planifiée ne le lance, aucun cycle ne l'importe. Source : yfinance,
barres d'un jour, clôture non ajustée, symbole du grand livre demandé tel quel.
- Pour chaque instrument qui a un trade : du jour de son premier trade jusqu'à la veille. Si des
  cours sont déjà stockés, seuls les 7 derniers jours et la suite sont redemandés.
- Le jour en cours (UTC) n'est jamais enregistré : sa barre n'est pas encore une clôture.
- Un jour déjà présent avec la même clôture n'est pas réécrit : relancer n'ajoute aucun doublon.
- Un symbole introuvable chez Yahoo est listé et n'empêche pas les autres.

À BLANC PAR DÉFAUT : les cours sont demandés à Yahoo, rien n'est écrit, le script affiche ce qu'il
ajouterait ; il travaille alors sur une copie en mémoire, le fichier du grand livre n'est pas ouvert
en écriture. Avec --appliquer : écriture. Sans grand livre, il n'y a aucun instrument : le script
s'arrête sans rien créer.

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\ledger_cours.py                (à blanc)
    .venv\\Scripts\\python.exe scripts\\ledger_cours.py --appliquer    (écrit)
"""

import argparse
import os
import sys
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import ledger  # noqa: E402
from importeurs import cours  # noqa: E402

LEDGER_DEFAUT = os.path.join(RACINE, "data", "ledger.db")


def lancer(grand_livre: str = LEDGER_DEFAUT, appliquer: bool = False, telecharger=None,
           aujourd_hui: date | None = None) -> int:
    """Importe les cours et affiche le rapport. Code de sortie : 0, ou 1 sans grand livre ou si
    aucun symbole n'a pu être lu."""
    if not os.path.isfile(grand_livre):
        print(f"ERREUR : grand livre introuvable ({grand_livre}). Aucun instrument, rien n'a été créé.")
        return 1
    # --appliquer : crée la table cours si le grand livre date d'avant elle ; à blanc : copie en mémoire
    conn = ledger.ouvrir(grand_livre) if appliquer else ledger.copie_en_memoire(grand_livre)
    try:
        rapport = cours.importer(conn, telecharger or cours.cloture_yfinance, aujourd_hui=aujourd_hui,
                                 appliquer=appliquer)
    finally:
        conn.close()
    print("Cours enregistrés." if appliquer else "À BLANC : rien n'a été écrit (--appliquer pour écrire).")
    print(f"  instruments avec un trade    : {rapport.instruments}")
    print(f"  clôtures ajoutées            : {rapport.ajoutes}")
    print(f"  clôtures déjà présentes      : {rapport.deja_presents}")
    print(f"  valeurs invalides écartées   : {rapport.ecartes}")
    for symbole, raison in rapport.introuvables:
        print(f"  introuvable chez Yahoo : {symbole} ({raison})")
    tous_introuvables = rapport.instruments > 0 and len(rapport.introuvables) == rapport.instruments
    return 1 if tous_introuvables else 0


def main(argv: list[str] | None = None, telecharger=None) -> int:
    p = argparse.ArgumentParser(description="Cours de clôture vers le grand livre (à blanc par défaut).")
    p.add_argument("--appliquer", action="store_true", help="écrire dans le grand livre ; sinon à blanc")
    p.add_argument("--ledger", default=LEDGER_DEFAUT, help="grand livre")
    args = p.parse_args(argv)
    return lancer(args.ledger, args.appliquer, telecharger)


if __name__ == "__main__":
    sys.exit(main())
