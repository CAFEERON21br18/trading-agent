"""
scripts/rejeu_donnees.py — Barres quotidiennes du rejeu : téléchargement dans le cache et contrôles.

Outil manuel : aucune tâche planifiée ne le lance, aucun cycle ne l'importe. Univers :
data/watchlist.json.exemple. Source : yfinance, barres d'un jour depuis le 01/01/2017, ajustées des
divisions d'actions et des dividendes. Cache : data/rejeu/barres/ (hors git).
Un titre déjà en cache n'est PAS retéléchargé : le rejeu relit toujours les mêmes barres. Avec
--rafraichir, tout est retéléchargé (à ne pas faire après le premier lancement du rejeu, sauf à
le noter dans docs/REJEU_JOURNAL.md : les barres font partie de ce qui est figé).

Lancement, depuis la racine du dépôt :
    .venv\\Scripts\\python.exe scripts\\rejeu_donnees.py
"""

import argparse
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from rejeu import donnees  # noqa: E402


def lancer(rafraichir: bool = False, telecharger=None, dossier: str | None = None, aujourd_hui=None) -> int:
    """Remplit le cache, affiche les contrôles. Code de sortie : 0, ou 1 si aucun titre n'est utilisable."""
    tickers = list(donnees.univers())
    faits = donnees.preparer_cache(tickers, telecharger or donnees.telecharger_yfinance,
                                   aujourd_hui=aujourd_hui, dossier=dossier, rafraichir=rafraichir)
    barres, controles = donnees.charger(tickers, dossier)
    print(f"Titres de l'univers : {len(tickers)} ; téléchargés à ce lancement : {len(faits)} ; "
          f"utilisables : {len(barres)}")
    print(f"Empreinte du cache : {donnees.empreinte(tickers, dossier)[:16]}")
    for ticker in tickers:
        c = controles[ticker]
        etat = "utilisable" if c.utilisable else "ÉCARTÉ : " + " ; ".join(c.raisons)
        print(f"  {ticker:<9} {c.barres:>5} barres  {c.premiere} au {c.derniere}  "
              f"sans prix {c.sans_prix}  doublons {c.doublons}  trous {len(c.trous)}  {etat}")
    return 0 if barres else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Barres quotidiennes du rejeu : cache et contrôles.")
    p.add_argument("--rafraichir", action="store_true", help="retélécharger même les titres déjà en cache")
    return lancer(p.parse_args(argv).rafraichir)


if __name__ == "__main__":
    sys.exit(main())
