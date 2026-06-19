# Sous-Agent — Knowledge (Base de connaissances théoriques)

## Rôle
Bibliothèque de savoir théorique qu'AlphaSignal consulte avant chaque
décision importante. Comme un trader pro qui aurait Hull, Murphy,
Graham et Wyckoff dans sa tête.

## Fichiers
- `knowledge_base.py` : savoir structuré par domaines (technique, fondamental, macro, risk, psycho)
- `chart_reading.py`  : lecture multi-timeframe (structure, niveaux, patterns, confluence)
- `valuation.py`      : ratios + méthodes de valorisation
- `playbooks.py`      : scénarios types

## Quand consulter
- Cycles QUOTIDIEN et STRATEGIQUE → analyse APPROFONDIE (8 sections)
- Cycle TACTIQUE (15 min) → version CONDENSÉE (sections 1, 7, 8 uniquement)
- Cycle CRITIQUE → pas de consultation (trop coûteux)

## Règle anti-paralysie
Le savoir éclaire la décision, il ne la bloque pas. Si la knowledge_base
n'a pas d'info sur un sujet → fallback sur les indicateurs techniques de base.
