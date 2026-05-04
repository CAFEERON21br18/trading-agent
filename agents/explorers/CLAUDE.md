# Sous-Agents Explorers (règles communes)

## Rôle
Les explorateurs scannent l'univers de marché de leur catégorie pour identifier
des **opportunités** que les analystes n'ont pas dans la watchlist actuelle.

L'explorateur **recommande** — le Decision Engine **décide** — le Budget Manager **finance**.

## Pipeline d'une découverte
```
Universe (top N actifs) → Screener (filtres + score) → Queue (explorer_queue.json)
   → Email "🔍 OPPORTUNITÉ" si score ≥ 8 → Decision Engine analyse → Budget Manager alloue
```

## Score de potentiel (1-10)
- 1-3 : actif suspect, ignorer
- 4-5 : à surveiller, pas urgent
- 6-7 : candidat sérieux, à analyser → ajout queue
- 8-10 : opportunité forte → email immédiat

## Limites globales (max watchlist + queue)
- **Max 30 actifs** dans la watchlist ACTIVE
- **Max 20 actifs** en OBSERVATION (queue)
- Si queue pleine → l'explorateur skip les nouveaux candidats moins forts

## Fréquences (par catégorie)
| Explorer | Fréquence |
|---|---|
| Crypto | 5-10 min, 24/7 |
| Stock | rotation : top movers 10min, sectoriel 2h, global 1×/jour |
| Index | 30 min en heures de marché, 2h sinon |
| ETF | 2h en heures US, 1× le soir sinon |
| Commodity | 30 min |
| Forex | 10 min |
| CFD Index | 15 min |

## Contexte géopolitique
Tous les explorateurs intègrent le contexte de `geopolitics.resume_contexte_geopolitique()` :
- Si conflit → boost score sur défense/énergie/or
- Si crise bancaire → boost score sur valeurs refuge
- etc.

## Règles
- Ne jamais explorer un actif déjà en watchlist active (sauf trade ouvert)
- Toujours documenter quels filtres ont déclenché le score (`filters_triggered`)
- Cache impératif (CoinGecko / yfinance ont des rate-limits)
- Try/except autour de chaque appel API
