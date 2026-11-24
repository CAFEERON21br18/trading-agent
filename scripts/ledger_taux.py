"""
scripts/ledger_taux.py — Clôture quotidienne EURUSD vers la table change du grand livre.

Outil manuel : aucune tâche planifiée ne le lance, aucun cycle ne l'importe. Source : yfinance,
ticker « EURUSD=X », barres d'un jour (dollars pour un euro).
- Un jour déjà présent dans la table n'est pas réécrit : relancer n'ajoute aucun doublon.
- Le jour en cours (UTC) est écarté : sa barre n'est pas encore une clôture.
- Période par défaut : de 7 jours avant le dernier taux stocké (365 jours en arrière si la table
  est vide) jusqu'à hier. --depuis et --jusqu-a (AAAA-MM-JJ) la remplacent.
- Cours indisponible : code de sortie 1, rien n'est écrit.

À BLANC PAR DÉFAUT : le cours est demandé à Yahoo, rien n'est écrit, le script affiche ce qu'il
ajouterait ; si le grand livre n'existe pas encore, il n'est pas créé. Avec --appliquer : écriture.

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\ledger_taux.py                       (à blanc)
    .venv\\Scripts\\python.exe scripts\\ledger_taux.py --appliquer           (écrit)
    .venv\\Scripts\\python.exe scripts\\ledger_taux.py --depuis 2026-09-01 --appliquer
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import ledger  # noqa: E402
from importeurs import taux_change  # noqa: E402

LEDGER_DEFAUT = os.path.join(RACINE, "data", "ledger.db")


def lancer(grand_livre: str = LEDGER_DEFAUT, appliquer: bool = False, depuis: date | None = None,
           jusqu_a: date | None = None, telecharger=None, aujourd_hui: date | None = None) -> int:
    """Importe les taux et affiche le rapport. Code de sortie : 0, ou 1 si le cours est indisponible."""
    aujourd_hui = aujourd_hui or datetime.now(timezone.utc).date()
    # À blanc et sans grand livre existant : base en mémoire, aucun fichier créé
    chemin = grand_livre if appliquer or os.path.exists(grand_livre) else ":memory:"
    conn = ledger.ouvrir(chemin)
    try:
        debut, fin = taux_change.periode_par_defaut(conn, aujourd_hui)
        debut, fin = depuis or debut, jusqu_a or fin
        if debut > fin:
            print(f"ERREUR : période vide ({debut} après {fin}).")
            return 1
        rapport = taux_change.importer(conn, debut, fin, telecharger or taux_change.cloture_yfinance,
                                       aujourd_hui=aujourd_hui, appliquer=appliquer)
    except taux_change.SourceIndisponible as exc:
        print(f"ERREUR : {exc}. Rien n'a été écrit.")
        return 1
    finally:
        conn.close()
    print("Taux enregistrés." if appliquer else "À BLANC : rien n'a été écrit (--appliquer pour écrire).")
    print(f"  période demandée   : {debut} au {fin}")
    print(f"  jours ajoutés      : {rapport.ajoutes}"
          + (f" ({rapport.premier} au {rapport.dernier})" if rapport.ajoutes else ""))
    print(f"  jours déjà présents : {rapport.deja_presents}")
    for jour, raison in rapport.ecartes:
        print(f"  écarté : {jour} ({raison})")
    return 0


def main(argv: list[str] | None = None, telecharger=None) -> int:
    p = argparse.ArgumentParser(description="Taux EURUSD quotidien vers le grand livre (à blanc par défaut).")
    p.add_argument("--appliquer", action="store_true", help="écrire dans le grand livre ; sinon à blanc")
    p.add_argument("--depuis", type=date.fromisoformat, help="premier jour, AAAA-MM-JJ")
    p.add_argument("--jusqu-a", dest="jusqu_a", type=date.fromisoformat, help="dernier jour, AAAA-MM-JJ")
    p.add_argument("--ledger", default=LEDGER_DEFAUT, help="grand livre")
    args = p.parse_args(argv)
    return lancer(args.ledger, args.appliquer, args.depuis, args.jusqu_a, telecharger)


if __name__ == "__main__":
    sys.exit(main())
