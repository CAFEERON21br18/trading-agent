"""
scripts/run_analysis.py — Lance une analyse quotidienne complète
Usage :
  python3 scripts/run_analysis.py               → analyse + email
  python3 scripts/run_analysis.py --no-email    → analyse sans email (test)
  python3 scripts/run_analysis.py --preview     → génère rapport mais ne l'envoie pas
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger         import get_logger
from agents.orchestrator  import lancer_routine_quotidienne, generer_rapport_quotidien

logger = get_logger(__name__)


def main():
    args = sys.argv[1:]
    envoyer_emails = "--no-email" not in args and "--preview" not in args

    print("\n" + "="*60)
    print("  AlphaSignal — Analyse quotidienne")
    print("="*60 + "\n")

    if "--preview" in args:
        # Juste générer et afficher, sans persistance ni email
        rapport, signaux = generer_rapport_quotidien()
        print(rapport)
        print(f"\n--- {len(signaux)} signaux forts détectés ---")
        return

    resume = lancer_routine_quotidienne(envoyer_emails=envoyer_emails)

    print("\n--- Résumé de la routine ---")
    print(f"  Signaux forts détectés  : {resume['signaux_forts']}")
    print(f"  Rapport email envoyé    : {'✅' if resume['rapport_envoye'] else '❌ ou désactivé'}")
    print(f"  Alertes envoyées        : {resume['alertes_envoyees']}")
    print(f"  Alerte dégradation      : {'⚠️  Oui' if resume['alerte_degradation'] else 'Non'}")


if __name__ == "__main__":
    main()
