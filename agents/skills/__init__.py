"""
agents/skills/ — 5 skills de raisonnement réutilisables (v5.3.8).

Ces fonctions sont des outils mentaux que tout module peut invoquer
(decision_engine, chat, plan_advisor, etc.). Chacune retourne un dict
structuré. Toutes ont un fallback gracieux : champ "disponible": False
si Gemini est KO.

Skills :
  bayesien        : révision bayésienne d'une hypothèse (prior → posterior)
  pre_mortem      : "Si ça a échoué dans 6 mois, pourquoi ?"
  second_ordre    : effets de 2e ordre / boucles / conséquences cachées
  base_rates      : taux de base de la classe de référence vs cas particulier
  metacognition   : audit du raisonnement lui-même

Usage :
    from agents.skills import pre_mortem
    r = pre_mortem.executer(decision="BUY NVDA 50€", contexte="...")
    for s in r["scenarios_echec"]: print(s)
"""

from agents.skills import bayesien, pre_mortem, second_ordre, base_rates, metacognition

__all__ = ["bayesien", "pre_mortem", "second_ordre", "base_rates", "metacognition"]
