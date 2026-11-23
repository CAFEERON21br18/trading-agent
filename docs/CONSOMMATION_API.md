# Consommation des API — 06/10 au 19/10/2026

Document de mesure, pour choisir les offres. Il ne décide rien et ne contient aucune clé, aucun
rendement, aucune donnée du portefeuille réel. Comptages, fréquences, erreurs seulement.

## 1. Sources, et ce qu'elles ne disent pas

- **Les journaux des 14 derniers jours n'existent plus.** Les fichiers qui gardaient l'historique des
  cycles (task_tactical, task_strategic, task_daily, tactical, strategic, daily…) contenaient la clé
  NewsAPI ; ils ont été supprimés le 19/10 et recréés à 13h30. Restent : `task_critical.log` (aucun
  appel de fournisseur), `task_weekly.log`, et les journaux du 19/10 depuis 13h30.
- **Mesuré sur toute la période** :
  - le registre (`data/registre.db`) : passages des cycles, décisions, statut du pipeline groupé par
    décision (`execute` = un appel LLM, `cache`, `saute`) et son fournisseur ;
  - `message_audit` : chaque tentative LLM du chat (fournisseur, succès, type d'erreur) ;
  - `jev_observations` : chaque appel TypeSafe (statut, erreur, jetons, latence).
- **Mesures plus anciennes, datées, reprises du dépôt** : TODO §2 (Groq, 01/10), TODO §2 et Q5
  (Gemini), TODO §14 (NewsAPI, 06/10), TODO §27 (Alpha Vantage, 25/09–08/10).
- **Estimé** : NewsAPI, Alpha Vantage, CoinGecko et Yahoo ne journalisent que leurs échecs ; leurs
  succès ne sont écrits nulle part. Les volumes ci-dessous sont des **demandes estimées** : chaque
  décision du registre est une analyse complète, et la logique de cache est lue dans le code
  (`utils/cache.py`, `news_fetcher.py`, `alphavantage.py`, `onchain.py`, `data_fetcher.py`).

## 2. Tableau par fournisseur

| Fournisseur | Limite gratuite connue (source) | Appels par jour | Échecs observés | Quota épuisé vers | Qui consomme |
|---|---|---|---|---|---|
| **Gemini** | 20 requêtes/jour, 5/minute (quotaValue lu dans les réponses de Google, TODO §2 / Q5) ; remise à zéro vers 01h00 Lisbonne | attendu par le code depuis Q4 : 1 par jour (narratif quotidien), + 1 le dimanche (narratif hebdo, réussi les 11 et 18/10 d'après `task_weekly.log`), + le chat (0 à 6 tentatives par jour d'utilisation). Inventaire du 05/10, avant Q1–Q4 : environ 1 200 appels LLM/jour tous fournisseurs, 20 % aboutis | chat : `quota_quotidien` les 01/10 (22h55), 03/10 (17h32), 06/10 (16h31–17h17) ; 41 965 refus « par jour » dans les journaux jusqu'au 06/10 | avant Q4 : dans l'heure qui suit la remise à zéro ; depuis Q4 : non atteint (réservé à chat, narratif_quotidien, narratif_hebdo) | `utils/llm.ask_llm` (appelants réservés), chat |
| **Groq** | 200 000 jetons/jour (TPD, message d'erreur du 01/10, TODO §2) | mesuré : pipeline groupé 0 à 16 appels/jour pour les cycles + 250 sur la période pour le conseiller réel ; conseiller réel : 1 appel par position réelle et par passage stratégique (6/jour) ; chat : 0 à 4 | chat : `rate_limit_groq` (TPD épuisé) les 01/10 et 03/10 ; pipeline : 5 replis « both_failed » le 06/10, aucun depuis | 01/10 et 03/10 dans la soirée ; non atteint depuis Q2 (cache du pipeline) et Q4 | pipeline groupé (`agents/skills`), conseiller réel, chat, narratifs en repli |
| **NewsAPI** | 100 requêtes/jour (`.env.example`) | demande estimée : 470 à 820 recherches par actif et par demi-heure, + 55 à 120 requêtes de géopolitique, + 10 au plus pour le rapport | 429 : 742 dans le journal du tactical le 06/10 (TODO §14) ; 4 entre 13h30 et 15h30 le 19/10 | estimé : dans les 3 premières heures après la remise à zéro (supposée à minuit UTC, non documentée dans le dépôt) ; 429 à toute heure ensuite | Sentiment Analyst (`news_fetcher`, toutes les analyses), géopolitique (explorateur matières premières, cache 1 h), rapport quotidien (section News) |
| **Yahoo RSS** (news, sans clé) | non documentée | même demande que NewsAPI, en repli | 429 (« Too Many Requests ») à chaque passage du tactical, relevé les 16–18/10 et le 19/10 | — | `news_fetcher.recuperer_news_yahoo_rss` |
| **Alpha Vantage** | 25 requêtes/jour, 5/minute (`alphavantage.py`, `.env.example`) | demande estimée : 100 à 370 OVERVIEW/jour (une par analyse d'AAPL, TSLA, NVDA, MSFT, AMZN, sans cache), + EARNINGS quand OVERVIEW aboutit | « limite atteinte » : 405 à 468 par jour du 25/09 au 08/10, environ 20 par heure (TODO §27) ; 5 entre 13h30 et 15h30 le 19/10 | dans la première heure après la remise à zéro ; le cycle de 7h30 n'a reçu aucune donnée depuis le 24/09 (TODO §27) | Fundamental Analyst (`analyser_action`) |
| **CoinGecko** (sans clé) | « 50 req/min, 10 000/mois » (commentaire de `crypto_explorer/universe.py`) ; l'API publique sans clé limite plus bas en pratique | demande estimée : 120 à 460 appels/jour (données de BTC, ETH, SOL + dominance BTC à chaque analyse, sans cache pendant la période mesurée ; cache de 10 min depuis, `onchain.py`) + 24 (top 50, cache 1 h) | 429 sur la dominance BTC et sur les données de la crypto à chaque passage du tactical (16–18/10) | par minute (rafales d'un passage), pas par jour | Fundamental Analyst (`onchain.py`), explorateur crypto (univers) |
| **yfinance / Yahoo** (sans clé) | aucune limite publiée | estimé : environ 19 000 téléchargements/jour pour les explorateurs (207 actifs par passage × 6 mois de barres, cache de 5 min plus court que le passage de 15 min), + 1 prix par position paper toutes les 5 min (critique), + la collecte quotidienne (51 séries : 5 cryptos × 3 unités de temps, 18 autres actifs × 2) | aucune erreur au dernier passage des explorateurs (heartbeat du 19/10, 15h15 à Lisbonne) ; 429 sur les flux RSS Yahoo (même domaine) | — | explorateurs (`data_fetcher`), Paper Trader (`portfolio.prix_actuel`), collecte (`fetch_data`), prix réels (`real_price`), chat (hors watchlist) |
| **TypeSafe** (Jev) | non documentée dans le dépôt | mesuré : 23 par jour (une observation par actif de la watchlist, cycle quotidien), depuis le 09/10 | aucune erreur (253 appels) | — | `agents/jev/observer.py` |

## 3. Par jour (06/10 partiel depuis R2 à 19h30, 19/10 partiel jusqu'à 15h30)

Pipeline : appels LLM réels (`execute`, origine cycle) et réponses servies par le cache du jour.
NewsAPI : recherches par actif et par demi-heure + géopolitique (5 requêtes par heure de tactical).
Alpha Vantage : OVERVIEW demandés. CoinGecko : appels demandés, top 50 compris. Yahoo : téléchargements
des explorateurs. TypeSafe : observations de Jev. Colonnes 6 à 9 : demandes estimées.

| Jour | Passages tactical | Décisions (registre) | Pipeline : appels | Pipeline : cache | NewsAPI demandé | Alpha Vantage demandé | CoinGecko demandé | Yahoo (explorateurs) | TypeSafe |
|---|---|---|---|---|---|---|---|---|---|
| 06/10 | 17 | 229 | 0 | 102 | 130 + 25 | 35 | 24 | ≈ 3 519 | 0 |
| 07/10 | 93 | 1280 | 12 | 397 | 748 + 120 | 135 | 30 | ≈ 19 251 | 0 |
| 08/10 | 91 | 1254 | 13 | 355 | 821 + 115 | 102 | 292 | ≈ 18 837 | 0 |
| 09/10 | 91 | 1254 | 16 | 390 | 780 + 115 | 128 | 464 | ≈ 18 837 | 23 |
| 10/10 | 93 | 1280 | 13 | 528 | 758 + 120 | 197 | 216 | ≈ 19 251 | 23 |
| 11/10 | 94 | 1285 | 13 | 564 | 789 + 120 | 198 | 218 | ≈ 19 458 | 23 |
| 12/10 | 92 | 1267 | 13 | 487 | 778 + 115 | 195 | 214 | ≈ 19 044 | 23 |
| 13/10 | 92 | 1267 | 11 | 297 | 824 + 115 | 196 | 316 | ≈ 19 044 | 23 |
| 14/10 | 92 | 1267 | 9 | 167 | 788 + 115 | 244 | 292 | ≈ 19 044 | 23 |
| 15/10 | 95 | 1306 | 10 | 267 | 809 + 120 | 374 | 444 | ≈ 19 665 | 23 |
| 16/10 | 82 | 1129 | 7 | 246 | 674 + 105 | 338 | 358 | ≈ 16 974 | 23 |
| 17/10 | 42 | 585 | 7 | 165 | 333 + 55 | 175 | 120 | ≈ 8 694 | 23 |
| 18/10 | 89 | 1220 | 5 | 356 | 704 + 115 | 366 | 208 | ≈ 18 423 | 23 |
| 19/10 | 58 | 809 | 6 | 232 | 473 + 75 | 241 | 146 | ≈ 12 006 | 23 |

Le 17/10, le tactical n'a fait que 42 passages (le registre n'en a pas d'autres) : à vérifier à part.

## 4. Ce qui manque aujourd'hui faute de quota

Registre, décisions d'origine « cycle » du 07/10 au 19/10 :

| Classe d'actifs | Décisions | Sentiment à confiance 0 (aucune news) | Fondamental à confiance 0 |
|---|---|---|---|
| Cryptos de la watchlist (5) | 3 677 | 85,9 % | 60,3 % |
| 5 actions de `ACTIONS_US` | 2 814 | 82,3 % | 0 % (repli sur la fourchette 52 semaines) |
| 7 autres actions (VRT, AMAT, AMD, MU, LITE, VST, CEG) | 2 334 | 85,8 % | 100 % (type « inconnu », pas de quota en cause, TODO §27) |
| ETF et CFD (6) | 282 | 87,2 % | 4,6 % |
| Queue des explorateurs | 5 505 | 85,4 % | 100 % |

- **Sentiment** : plus de 8 analyses sur 10 n'ont aucune news (NewsAPI épuisé, Yahoo RSS en 429) ;
  le poids de 20 % du sentiment ne joue presque jamais. Les analyses qui ont des news sont réparties à
  toute heure (repli Yahoo quand il répond), pas seulement après la remise à zéro de NewsAPI.
- **Fondamental des actions US** : ni P/E, ni EPS, ni earnings depuis le 24/09 au cycle de 7h30
  (Alpha Vantage épuisé par le tactical) ; seule reste la position dans la fourchette de 52 semaines.
- **Fondamental crypto** : HBAR et CRO n'ont pas de correspondance CoinGecko ; BTC, ETH et SOL perdent
  une partie de leurs données sur les 429 par minute de CoinGecko (voir le diagnostic SOL).
- **Géopolitique** : construite sur NewsAPI, presque toujours vide ; l'intuition ne reçoit presque
  jamais d'« actifs à surveiller ».
- **Rapport quotidien** : la section News affiche souvent « non disponible ».
- **LLM** : l'audit métacognitif est coupé (Q1) et Gemini est réservé au chat et aux narratifs (Q4)
  pour tenir dans 20 requêtes/jour ; le pipeline passe par Groq et tient dans le TPD grâce au cache.

## 5. Ce qu'il faudrait pour mesurer exactement (non fait)

Une ligne par appel abouti chez NewsAPI, Alpha Vantage, CoinGecko et Yahoo (succès, refus, type de
refus, heure), ou un compteur par jour et par fournisseur comme `data/rapport_newsapi.json` ; sans
cela, les volumes de NewsAPI, Alpha Vantage, CoinGecko et Yahoo restent des demandes estimées.
