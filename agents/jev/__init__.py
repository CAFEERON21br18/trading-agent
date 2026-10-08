"""
agents/jev/ — Observation du modèle Jev (TypeSafe), SANS effet sur les décisions.

Branché uniquement dans le cycle quotidien (agents/orchestrator.py), après la
décision du moteur. Aucune réponse de Jev n'est lue par le vote, le Budget
Manager ou le Paper Trader : elles sont seulement enregistrées dans la table
jev_observations, puis lues par scripts/jev_bilan.py selon le critère
pré-enregistré dans docs/REGISTRE_CRITERES.md §7.
"""
