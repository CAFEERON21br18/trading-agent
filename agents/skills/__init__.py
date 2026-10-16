"""
agents/skills/ — Pipeline de raisonnement du Decision Engine (v5.4.0, Phase 4 / Q2).

pipeline_grouped : un seul appel LLM groupé produit les cinq analyses (bayésienne,
pré-mortem, second ordre, base rates, métacognition) ; pipeline_cache : une analyse
par actif, action et jour, sinon mode Prudent. Les anciens skills séparés (un appel
Gemini chacun) et pipeline.py ont été supprimés (TODO §10) : aucun module ne les
appelait. Le paquet n'importe rien : importer un module ne charge que lui.
"""
