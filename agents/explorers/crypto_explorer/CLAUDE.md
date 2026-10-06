# Crypto Explorer

## Univers
Top 50-300 cryptos par market cap (via CoinGecko API gratuite).
**Exclut** : stablecoins (USDT, USDC, DAI…) et wrapped tokens (WBTC, WETH…).

## Fréquences
- Scan rapide top 50 + alertes volume : toutes les 10 min (cycle tactique)
- Scan complet top 300 : toutes les 2h (cycle stratégique)
- Scan ciblé si news crypto détectée : immédiat

## Filtres V1 implémentés
1. **MOMENTUM** : RSI 55-75 + MACD haussier + prix > EMA20 → +2
2. **VOLUME EXPLOSIF** : volume 24h > 3× moyenne 7j en USD → +2
3. **POTENTIEL FONDAMENTAL** : market cap < 10B$ ET volume > 5M$/j → +2
4. **ANOMALIE** : chute > 15% en 24h sur top 50 → +2 (potentiel rebond)
5. **Bonus convergence** : si 3+ filtres déclenchent → +2

## Filtres V2 (à venir)
- BREAKOUT : prix casse plus haut 30j avec volume
- NARRATIVE : actif lié à un narratif en croissance (IA, RWA, DePIN, L2)
- ON-CHAIN : hausse adresses actives ou TVL

## Cache
- Données CoinGecko : TTL 1h (catégorie `coingecko_top`)
- OHLCV yfinance : TTL 5 min (catégorie `prix_ohlcv`)

## Règles
- Ne re-scanner un ticker déjà en watchlist active que si position ouverte
- Toujours classer la découverte dans `explorer_queue.json` si score ≥ 4
  (seuils réels : `agents/explorers/base.py`)
- Email immédiat si score ≥ 7
