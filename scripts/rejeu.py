"""
scripts/rejeu.py — Lance le rejeu sur plusieurs années du cœur technique (registre §10).

Outil manuel : aucune tâche planifiée ne le lance, aucun cycle ne l'importe, aucune décision de
l'agent ne change. Il APPELLE les fonctions de l'agent sur les barres du cache
(scripts/rejeu_donnees.py d'abord), pour les six configurations (100 €, 1 000 €, 10 000 € ×
« Revolut », « CFD »), et les compare à « acheter et garder ».
Sorties, toutes hors git : data/rejeu/ledger_rejeu.db (grand livre du rejeu, jamais
data/ledger.db), data/rejeu/lancement.json, reports/rejeu/RAPPORT.md. Les sorties du lancement
précédent sont archivées, pas effacées. Ni réseau, ni LLM, ni e-mail pendant le rejeu.

Lancement, depuis la racine du dépôt (quelques minutes) :
    .venv\\Scripts\\python.exe scripts\\rejeu_donnees.py
    .venv\\Scripts\\python.exe scripts\\rejeu.py
"""

import argparse
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "rejeu-sans-email")  # config.py les exige ; le rejeu n'envoie aucun e-mail


def lancer(processus: int | None = None) -> int:
    """Lance le rejeu et affiche le verdict. Code de sortie : 0, ou 1 si l'agent a journalisé des erreurs."""
    from rejeu import etude, lancement
    from rejeu import parametres as P
    resume = lancement.lancer(processus=processus or max(1, min(12, (os.cpu_count() or 2) - 2)))
    decide = etude.lire(configs=[P.CONFIG_QUI_DECIDE])[0]
    d = resume["durees_s"]
    print(f"Rejeu terminé en {d['total']} s (analyses {d['analyses']} s, simulations {d['simulations']} s).")
    print(f"Verdict (1 000 €, Revolut, {P.ANNEES[0]}–{P.ANNEES[-1]}, {decide.periode.trades} trades clos) : "
          f"« {decide.verdict} »")
    for c in decide.conditions:
        print(f"  {c.numero}. {'VRAIE ' if c.vraie else 'FAUSSE'} — {c.constat}")
    print(f"Rapport : {resume.get('rapport')}")
    erreurs = sum(c["erreurs_agent"] for c in resume["configurations"])
    if erreurs:
        print(f"ATTENTION : {erreurs} erreur(s) journalisée(s) par l'agent pendant le rejeu (data/rejeu/lancement.json).")
    return 1 if erreurs else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rejeu sur plusieurs années du cœur technique de l'agent.")
    p.add_argument("--processus", type=int, help="nombre de processus (défaut : selon la machine, 12 au plus)")
    return lancer(p.parse_args(argv).processus)


if __name__ == "__main__":
    sys.exit(main())
