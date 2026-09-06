# Technical Skills — 10 outils quantitatifs

## Rôle
Skills purs Python (peu ou pas de LLM) qui rendent l'agent plus précis
et plus informé. Aucun impact sur les quotas Gemini/Groq.

## Skills

| Skill | Fichier | v |
|---|---|---|
| 1. Régime de marché | market_regime.py | 5.5.0 |
| 2. Trailing stop intelligent | trailing_stop.py | 5.5.1 (à venir) |
| 3. Score qualité A/B/C | setup_quality.py | 5.5.2 (à venir) |
| 4. Corrélation dynamique | correlation.py | 5.5.3 (à venir) |
| 5. Calendrier économique | economic_calendar.py | 5.5.4 (à venir) |
| 6. Liquidité | liquidity.py | 5.5.5 (à venir) |
| 7. News catalyst | news_catalyst.py | 5.5.6 (à venir) |
| 8. Scénarios / stress tests | scenario_simulation.py | 5.5.7 (à venir) |
| 9. Backtester renforcé | backtester_pro.py | 5.5.8 (à venir) |
| 10. Attribution performance | performance_attribution.py | 5.5.9 (à venir) |

## Convention
Chaque skill expose :
- Une fonction d'analyse principale (ex : `detecter_regime_actif`)
- Une fonction d'enregistrement (ex : `enregistrer_regime`)
- Une fonction de lecture (ex : `dernier_regime`)

## Intégration
Les skills se branchent aux points existants :
- Cycle stratégique (4h) → analyse + persistance
- Decision Engine → lecture via `analyses["context"]`
- Dashboard → endpoints `/api/regime`, `/api/correlation`, ...
