# Explorateurs : diagnostic et brouillon de critère (19/10/2026)

**Statut : brouillon à valider.** Ce fichier ne modifie pas `docs/REGISTRE_CRITERES.md`
et ne décide rien. Il contient seulement des comptages, des fréquences, des états et
des erreurs : aucun rendement, aucun P&L, aucun taux de réussite.

## 1. Sources (lecture seule)

- `data/heartbeat.json` : dernier passage de chaque explorateur (19/10, 14h45 UTC).
- `logs/tactical.log` du 19/10 (3 passages ; les journaux plus anciens ont été
  supprimés le 19/10 parce qu'ils contenaient la clé NewsAPI).
- Registre (`data/registre.db`, `mode=ro`) : décisions `source = "queue"` du 06/10 au 19/10.
- Rejeu hors ligne des filtres sur les barres du cache de production
  (`data/cache/prix_ohlcv`, âgées de 2 à 3 minutes, 19/10 vers 15h45), sans réseau.
- Code : `agents/explorers/` et `scripts/cycle_tactical.py` (étape 3).

## 2. Ce que fait chaque explorateur

Les 7 tournent à chaque passage du tactical, dans cet ordre : Crypto, Stock, Index,
ETF, Commodity, Forex, CFD Index. La watchlist est exclue du scan.

| Explorateur | Univers | Scannés / passage | Filtres (score) | Filtres morts | Téléchargement vide |
|---|---|---|---|---|---|
| Crypto | top CoinGecko hors stablecoins listés | 45 | 4 filtres, +2 chacun, +2 si ≥ 3 | aucun | 16 / 45 |
| Stock | 50 grandes capitalisations US | 44 | pack : momentum, breakout, volatilité, golden cross | golden cross | 0 |
| Index | `INDICES_MONDIAUX` | 20 | momentum, volatilité, golden cross, death cross | les 2 croisements | 1 (`^FTMIB`) |
| ETF | 47 ETF US | 44 | comme Stock | golden cross | 0 |
| Commodity | `COMMODITIES_FUTURES` | 16 | momentum, breakout, volatilité (+2 géopolitique) | aucun | 0 |
| Forex | majeurs, croisés, exotiques | 20 (18 distincts) | momentum, breakout, volatilité | aucun | 0 |
| CFD Index | 18 indices | 18 | comme Index | les 2 croisements | 1 (`^FTMIB`) |

Total : 207 actifs scannés par passage. Barème du pack (`screening_helpers.appliquer_pack`) :
1 filtre donne 4, 2 filtres 6, 3 filtres ou plus 10. Pour Crypto, 1 filtre donne 2,
sous le seuil de la queue (4) : il en faut 2.

**Filtres morts.** Les explorateurs téléchargent 6 mois de barres journalières, soit
121 à 131 barres. L'EMA 200 demande 200 barres : elle est vide sur les 5 dernières
barres de **tous** les actifs rejoués (160 sur 160). Le golden cross et le death cross
ne peuvent donc jamais se déclencher. Index et CFD Index n'ont plus que 2 filtres
vivants : leur score plafonne à 6.

**Doublons d'univers.** 17 des 18 indices de CFD Index sont aussi dans l'univers
d'Index (d'où 0,7 s par passage : tout vient du cache). Forex scanne deux fois
EURGBP=X et EURJPY=X (présents dans les majeurs et dans les croisés).

**Crypto sans barres (16 sur 45).** Des stablecoins ou fonds tokenisés absents de la
liste d'exclusion (USDS, USDE, USD1, USYC, USDY, BUIDL, FIGR_HELOC), et des symboles pour
lesquels Yahoo ne renvoie rien sous la forme `XXX-USD` (HYPE, SUI, TAO, UNI, entre autres). Un
stablecoin, USDG-USD, a été analysé depuis la queue.

## 3. Rejeu des filtres sur un instantané (19/10, vers 15h45)

| Explorateur | Score 0 | Score 2 | Score 4 | Score 6 | Filtres déclenchés |
|---|---|---|---|---|---|
| Crypto | 12 | 27 | 6 | 0 | potentiel fondamental 31, volume explosif 6, momentum 1, anomalie 1 |
| Stock | 18 | — | 26 | 0 | momentum 26 |
| ETF | 28 | — | 16 | 0 | momentum 16 |
| Index | 12 (+1 vide) | — | 7 | 0 | momentum 7 |
| Commodity | 11 | — | 5 | 0 | momentum 5 |
| Forex | 13 | — | 6 | 1 | momentum 7, volatilité 1 |
| CFD Index | 11 (+1 vide) | — | 6 | 0 | momentum 6 |

Le momentum seul (RSI > 50 et MACD haussier ou prix > EMA 20) suffit au score 4.
Sur cet instantané, 73 actifs sont à 4 ou plus, pour environ 5 places libres dans la queue.

## 4. Découvertes mises en queue

- Journal du 19/10 (3 passages) : Crypto 6 observations (score 4), Stock 9 observations,
  Forex 3 découvertes (score 6), tous les autres 0. Aucune erreur, aucun avertissement.
- Queue au moment du relevé : 15 entrées, Stock 9 et Crypto 6, toutes au score 4.
- Registre, du 06/10 au 19/10 (14 jours), décisions venues de la queue :

| Classe (d'après le ticker) | Tickers distincts | Couples (ticker, jour) | Part des couples | Analyses | Part des analyses |
|---|---|---|---|---|---|
| Actions | 30 | 233 | 60 % | 2 694 | 48 % |
| Crypto | 17 | 78 | 20 % | 497 | 9 % |
| Matières (futures) | 5 | 29 | 8 % | 595 | 11 % |
| ETF | 7 | 25 | 6 % | 796 | 14 % |
| Forex | 1 (USDMXN=X) | 14 | 4 % | 1 026 | 18 % |
| Indices | 7 | 7 | 2 % | 7 | 0,1 % |
| **Total** | **67** | **386** | | **5 615** | |

USDMXN=X revient à presque chaque passage avec un score de 6 : il est analysé en premier
et occupe à lui seul 18 % des analyses de la queue.

## 5. Raisons de rejet, de la plus fréquente à la plus rare

1. **Aucun filtre déclenché** (score 0), ou 1 seul pour Crypto (score 2) : 132 actifs
   sur 207 dans l'instantané.
2. **Queue pleine et égalité de score.** La queue garde 20 entrées. Après chaque
   passage, l'étape 3 en analyse 5 puis les retire : il en reste 15. Crypto et Stock
   passent en premier et comblent les 5 places avec des scores de 4. Ensuite, un
   nouveau venu ne remplace l'entrée la plus faible que s'il a un score **strictement**
   supérieur (`queue_manager.ajouter_decouverte`) : Index, ETF, Commodity, Forex et
   CFD Index n'entrent qu'avec un score de 6. Ces rejets ne sont pas journalisés.
3. **Déjà dans la queue avec un score égal** : rejeté sans trace.
4. **Téléchargement vide** : 16 cryptos, et `^FTMIB` pour Index comme pour CFD Index.
   Une réponse vide est mise en cache 5 minutes, et l'actif reçoit 0 sans erreur comptée.
5. **429 de Yahoo sur les prix** : aucune trace aujourd'hui (aucun « Fetcher prix_ohlcv
   … échoué » dans les journaux actuels). Les 429 du 19/10 concernent les flux RSS de
   news, pas les barres. Les 14 jours précédents ne sont plus mesurables (journaux supprimés).

## 6. Pourquoi les actions et les ETF semblent rares

- **Comme découvertes (score ≥ 6), oui** : le golden cross est mort, et le breakout
  (prix à 1 % du plus haut sur 20 jours et volume 1,3 fois la moyenne) ne s'est pas
  déclenché dans l'instantané. Une action ou un ETF plafonne donc à 4, compté
  « observation » et pas « découverte » dans le heartbeat et dans la page Explorers,
  qui affichent 0 découverte pour Stock et ETF.
- **Dans la queue, les actions ne sont pas rares** : 60 % des couples, mais toujours au score 4.
- **Les ETF, eux, sont bloqués par l'ordre** : l'explorateur ETF passe en quatrième,
  quand la queue est déjà pleine de scores 4. Dans l'instantané, 16 ETF sur 44 étaient
  à 4 ; aucun n'a pu entrer.
- Univers réduits et fixes : 50 actions et 47 ETF, moins la watchlist.

## 7. Pourquoi aucune découverte n'est analysée (TODO §14)

Les indicateurs ne lisent que la table `prices`, alimentée seulement pour les 23 actifs
de la watchlist. Les explorateurs excluent justement la watchlist. Résultat : **aucun des
67 tickers analysés depuis la queue n'a de barre dans `prices`**. Sur 5 615 décisions,
5 600 sont marquées `sans_donnees` (HOLD 5 513, BUY 78, SELL 9). Les 15 autres sont des
HOLD « non soumises » du 06/10, avant le marquage R2c. Les 6 mois de barres téléchargés
par l'explorateur sont jetés après le score.

## 8. Brouillon de critère (à reporter au registre si tu le valides)

**Question.** Faut-il brancher les découvertes à l'analyse complète, c'est-à-dire
collecter leurs prix (option (a) du §14), puis les laisser ouvrir des positions paper ?

**Préalables, à corriger et dater AVANT le début de la mesure** (sinon le critère mesure
des défauts connus) :
- P1 : télécharger au moins 1 an de barres pour les explorateurs, ou retirer les
  croisements EMA 50/200 ;
- P2 : règle d'entrée dans la queue sans biais d'ordre (quota par explorateur, ou
  départage par ancienneté), et journal des rejets « queue pleine » ;
- P3 : exclure les stablecoins et fonds tokenisés, signaler les symboles sans barres ;
- P4 : collecte des prix des tickers de la queue en **mode ombre** : décisions inscrites
  au registre sous une origine distincte, aucune position paper.

**Étape 1 : critère structurel, sans rendement, lu à 4 semaines de mode ombre.**

| Mesure | Unité | Seuil proposé |
|---|---|---|
| Couples (ticker, jour) de la queue avec ≥ 200 barres 1d et une dernière barre ≤ 1 jour ouvré | couples | ≥ 95 % |
| Part des analyses venues de la queue qui restent `sans_donnees` | décisions | ≤ 2 % |
| Téléchargements Yahoo ajoutés par jour, et part de 429 sur ces téléchargements | appels | ≤ 500 / jour, 429 ≤ 1 % |
| Allongement du passage tactical (p90) | secondes | ≤ +15 s |
| Part des analyses de la queue prise par un seul ticker | décisions | ≤ 20 % |
| Couples distincts par classe (actions, ETF, crypto, matières, forex, indices) | couples | ≥ 10 par classe présente |

Si un seuil n'est pas tenu, on corrige et on recommence les 4 semaines. On ne passe pas
à l'étape 2.

**Étape 2 : critère d'effet, lu selon les règles communes du registre (§0).**
- Unité : décision BUY/SELL de la queue en mode ombre, dédupliquée par couple (ticker, jour, action).
- Observation indépendante à J+5 : un couple (classe, semaine ISO). Ces actifs sont
  « comptés seuls » au sens du §0.1.
- Métrique primaire : celle du §0.2 (rendement orienté à J+5, net des coûts du registre),
  comparée aux décisions de la watchlist de même tranche de score sur les mêmes semaines.
- Volume attendu : 6 classes au plus, donc 6 observations indépendantes par semaine
  au maximum. Avec n = 60, la lecture tombe vers 10 semaines au plus tôt ; échéance proposée
  à 20 semaines.
- Règle proposée : brancher (positions paper autorisées) si la queue n'est pas
  inférieure à la watchlist au-delà d'une marge fixée d'avance ; sinon option (b) du §14
  (ne plus analyser la queue, les explorateurs ne servant qu'aux alertes).

**Ce qu'il te reste à fixer** : la marge de non-infériorité de l'étape 2, n, et si l'étape 2
reste dans le mode ombre ou passe en micro-positions d'apprentissage.
