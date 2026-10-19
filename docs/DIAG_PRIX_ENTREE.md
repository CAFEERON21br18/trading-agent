# Prix d'entrée des positions paper : diagnostic (19/10/2026)

**Statut : diagnostic en lecture seule.** Aucun code n'est modifié. Ce document contient des
durées, des âges de prix, des comptages et des mécanismes. Il ne contient aucun rendement,
aucun P&L, aucun taux de réussite, ni de répartition des fermetures entre stop et objectif.

Sources : `positions` et `prices` (`data/database.db`), registre (`data/registre.db`), en `mode=ro`.

## 1. Le mécanisme, de la collecte à la fermeture

1. **Collecte des prix, une fois par jour.** La tâche quotidienne a deux déclencheurs, 07:30 et
   12:00 (`scripts/install_tasks_windows.ps1:66-67`). Mais le passage de 12:00 s'arrête si le
   rapport du jour existe (`scripts/cycle_daily.py:29-32`, `:76-77`) : ce n'est qu'un rattrapage.
   La collecte (`scripts/cycle_daily.py:94-102` → `scripts/fetch_data.py:116`, `:131`) écrit les
   barres 1d, 1wk et 1 h dans `prices` (`utils/database.py:131-165`). Depuis le 06/10, toutes
   les barres 1d sont écrites vers 06h30 UTC. Aucune n'a été écrite le 17/10 (rattrapage le 18/10).
2. **Qui ouvre.** Seuls deux cycles ouvrent des positions (le stratégique et le critique ne font que surveiller) :
   - le tactical, toutes les 15 min (`scripts/cycle_tactical.py:55-82`, étapes 3 et 4) ;
   - le quotidien, juste après la collecte (`agents/orchestrator.py:138`).
3. **D'où vient le prix d'entrée.**
   - `agents/asset_analyzer.py:28` lit les barres 1d de `prices` (`utils/indicators.py:22-36`),
     et `:39` prend `prix` = la dernière clôture en base.
   - `agents/paper_trader/cycle.py:77` reprend ce prix et le passe au Risk Manager (`:82`).
   - `agents/paper_trader/executor.py:96` l'enregistre comme `entry_price`.

   Pour une action ouverte pendant la séance américaine, c'est la clôture de la veille. Pour une
   crypto, c'est le relevé de 06h30 UTC.
4. **SL et TP calculés sur ce prix.** Le stop est le plus proche de deux niveaux : entrée − 1,5 ATR
   journalier, ou support × 0,995 si le support est plus près
   (`agents/analysts/risk_manager/position_sizer.py:18-40`). L'objectif 1 est à 2 fois la distance
   du stop, l'objectif 2 à 3 fois (`:43-55`), appelés par `manager.py:101-102` du même dossier.
5. **Surveillance au cours du moment.**
   - Le critique tourne toutes les 5 min, à partir de minuit (`install_tasks_windows.ps1:54-55`,
     `scripts/cycle_critical.py:35-38`). Le tactical et le stratégique surveillent aussi, mais avant
     leurs ouvertures.
   - `agents/paper_trader/monitor.py:29` demande le dernier cours Yahoo
     (`agents/paper_trader/portfolio.py:24-37`, `history(period="1d")`, sans cache) et le compare au SL et au TP (`monitor.py:62-73`).
   - Hors séance, ce cours est la dernière clôture connue de Yahoo, plus récente que celle de `prices`.
6. **Fermeture rapide.** Si le marché s'est éloigné du prix figé de plus que la distance au SL ou
   au TP, la position est fermée au premier passage du critique (`executor.py:116`).
7. **Boucle.** Rien n'interdit de rouvrir un actif qui vient d'être fermé : la règle anti-doublon ne
   regarde que les positions ouvertes (`agents/paper_trader/rules.py:56-57`, `executor.py:79-80`). Au passage suivant
   du tactical, les barres sont les mêmes, donc la décision est la même. La position est rouverte au
   même prix figé, puis refermée. La boucle dure jusqu'à la collecte suivante, à 07:30.

## 2. Mesures

**Définitions.**
- Âge depuis la date de la barre = ouverture − date de la barre 1d utilisée (comparable aux 46 h du 19/10).
- Âge du prix observé = ouverture − moment où ce prix était le cours du marché, c'est-à-dire
  min(fin de séance, heure d'écriture de la barre).
- Fins de séance approchées : 20:00 UTC pour les actions et les ETF, 21:00 UTC pour les futures,
  minuit UTC pour les cryptos.
- Depuis R2, la barre et son heure d'écriture viennent du registre (`barre`, 69 ouvertures, plus une
  retrouvée dans `prices`). Avant R2, la barre est retrouvée par égalité exacte de clôture pour 77
  ouvertures sur 351. Les autres, surtout des cryptos, ne se retrouvent pas, car leurs barres ont été
  réécrites depuis (P10).

### 2.1 Âge du prix d'entrée à l'ouverture (heures : médiane, Q1-Q3)

| Population | n | Depuis la date de la barre | Prix observé |
|---|---|---|---|
| Depuis R2, toutes | 70 | 45,8 (40,7-50,1) | 25,9 (21,0-30,1) |
| Depuis R2, actions | 64 | 46,4 (42,6-50,5) | 26,4 (22,6-30,5) |
| Depuis R2, cryptos | 6 | 15,8 (12,0-27,5) | 9,3 (5,5-21,0) |
| Depuis R2, tactical | 68 | 45,9 (41,3-50,2) | 26,1 (22,1-30,2) |
| Depuis R2, quotidien | 1 (+1 inféré) | 6,5 | 0,0 (inféré : 10,5) |
| Depuis R2, ouverture le week-end | 31 | 50,5 (48,5-52,5) | 30,5 (28,8-32,5) |
| Depuis R2, en semaine | 39 | 42,3 (37,8-44,8) | 22,3 (18,0-24,8) |
| Depuis R2, hors boucles (§2.5) | 11 | 30,5 (15,8-37,8) | 10,5 (9,3-18,0) |
| Avant R2, barres retrouvées | 77 | 45,9 (37,8-51,8) | 25,9 (17,8-31,8) |
| Avant R2, ouverture un lundi | 6 | 85,1 (84,4-87,8) | 65,1 (64,4-67,8) |
| Avant R2, tactical (inféré par l'heure) | 65 | 47,9 (40,5-52,8) | 27,9 (20,5-32,8) |
| Avant R2, quotidien (inféré) | 12 | 30,6 (30,5-30,6) | 10,6 (10,5-10,6) |

Depuis R2, la barre utilisée avait été écrite 15,8 h avant l'ouverture en médiane (Q1 11,6, Q3 19,9).

**Même mesure sur toutes les décisions BUY/SELL du registre depuis R2** (le p0 du §0.2) : 5 748
décisions, âge du prix observé 25,7 h (15,5-42,3).

| Cycle et classe | n | Âge du prix observé |
|---|---|---|
| Tactical, actions/ETF | 4 173 | 30,8 h (21,8-49,5) |
| Tactical, cryptos | 1 398 | 12,3 h (6,3-19,8) |
| Quotidien, toutes classes | 177 | 10,5 h (4,8-33,5) |

### 2.2 Durée des positions fermées (médiane, Q1-Q3)

| Population | Fermées | Durée | < 5 min | < 1 h |
|---|---|---|---|---|
| Toutes | 418 | 4,1 min (2,2 min-52 min) | 291 (70 %) | 315 (75 %) |
| Avant R2 | 351 | 3,8 min (1,7 min-3,2 h) | 233 (66 %) | 255 (73 %) |
| Depuis R2 | 67 | 4,2 min (4,1-4,3 min) | 58 (87 %) | 60 (90 %) |
| Hors boucles, toutes | 105 | 3,4 j (18,5 h-8,1 j) | 16 (15 %) | 17 (16 %) |
| Hors boucles, depuis R2 | 8 | 37 h (11 h-4,9 j) | 1 | 1 |

### 2.3 Fermetures au premier passage de surveillance

- **Depuis R2 :** 58 des 67 fermetures (87 %) ont lieu au premier passage du critique après
  l'ouverture. Le registre le confirme pour chacune : la clôture est inscrite dans le passage
  critique de la première échéance de 5 minutes.
- **Sur toute la période :** 291 fermetures sur 418 (70 %) ont lieu moins de 5 minutes après
  l'ouverture. Je compte « moins de 5 minutes » parce qu'avant le 23/09 (launchd sur macOS), les
  passages n'étaient pas calés sur les multiples de 5 minutes. Avant R2, 130 de ces fermetures
  tombent même avant la première échéance théorique (90 s en médiane). Avec les journaux supprimés,
  je ne peux pas dire s'il s'agissait du premier passage décalé ou d'une surveillance dans le même passage.

### 2.4 Écart |p1/p0 − 1| entre prix d'entrée et premier prix de surveillance (sans signe)

| Mesure | n | Médiane (Q1-Q3) |
|---|---|---|
| Exact, fermées en moins de 5 min (p1 = prix de fermeture), toutes | 291 | 4,0 % (3,3-5,9) |
| Idem, depuis R2 | 58 | 3,3 % (3,25-3,29) |
| Idem, hors boucles | 16 | 2,7 % (1,2-5,2) |
| Approché, cryptos (barre 1 h à l'ouverture + 5 min), toutes | 274 | 3,8 % (2,7-6,3) |
| Idem, hors boucles | 63 | 1,1 % (0,6-2,8) |
| Idem, depuis R2 | 6 | 0,7 % (0,35-3,3) |
| Approché, décisions crypto du registre (tactical, barre 1 h de la décision) | 1 322 | 1,8 % (0,6-3,1) |
| Idem, décisions crypto du cycle quotidien | 30 | 0,2 % (0,1-0,5) |

Ce qu'on ne peut pas mesurer : l'écart des actions qui n'ont pas été fermées au premier passage,
faute de barres intrajournalières.

### 2.5 Les boucles

Une boucle, c'est 3 ouvertures ou plus du même actif au même prix d'entrée exact. Il y en a 16, qui
regroupent **313 des 421 positions (74 %)**. Depuis R2, deux boucles font 59 des 70 ouvertures :
- AMZN, du 09/10 16:46 au 10/10 07:15 (heure de Lisbonne) : 56 ouvertures, une toutes les 15 min,
  la nuit comprise ;
- AAPL, le 13/10 de 14:46 à 15:16 : 3 ouvertures.

Avant R2, 14 boucles :

| Date | Actifs |
|---|---|
| 07/05 | SOL 25 |
| 14/05 | NVDA 3 |
| 18/05 | SOL 14, ETH 26 |
| 28/05 | BTC 11, SOL 11 |
| 02-04/06 | BTC 17 et 3, NVDA 4, ETH 22, SOL 9 |
| 26-27/06 | MSFT 32 |
| 27-28/08 | SOL 73 |
| 05/09 | VRT 4 |

12 des 16 boucles s'arrêtent entre 05:54 et 07:29, juste avant la collecte de 07:30.

## 3. Impact sur les mesures (aucun rendement calculé)

| Mesure | Ce qui est faussé | Depuis |
|---|---|---|
| §0.2 p0, donc Q1 (seuil BUY et zone d'apprentissage), Q2, Q3.b | p0 est une clôture figée : 26 h en médiane pour le tactical, qui produit 97 % des BUY/SELL. La fenêtre de rendement commence avant la décision et compte un mouvement qu'aucun ordre ne pouvait capter. C'est un bruit sans signe d'environ 1,8 % en crypto (tactical). Ce n'est un biais que s'il est corrélé au sens de la décision, ce qui ne se vérifie qu'avec des rendements | 06/10 (R2), dès la 1re décision |
| Q3.a (verdicts) | Pas de prix. Le contexte du pipeline (`agents/skills/_memory_context.py:19-21`, `:79`) lit `utils/memory_lookups.py`, donc `signals` et `signal_results` (vide), pas les positions : pas de contamination par les boucles (corrigé le 19/10, session 8) | — |
| §7 Jev | p0 = prix du cycle quotidien juste après la collecte (`agents/jev/observer.py:62`) : clôture de la veille pour les actions (environ 10,5 h), environ 0 h pour les cryptos et les futures. Seul l'écart de la nuit compte. Indirect : `mode_bm`, `plafond_bm` et `taille_hypothetique` dépendent du mode du Budget Manager | 09/10 |
| §8 fantôme | Même p0 que le §7. Sortie à la 5e barre, sans SL/TP surveillé (`agents/jev/fantome_regles.py:68-76`), donc pas de boucle | 09/10 |
| P&L paper, statistiques du dashboard et du chat (lues dans `positions`) | 74 % des positions sont des artefacts de boucle | 07/05 |
| Winrate par actif | Lu dans `performance_tracker.md` (`agents/memory_reader.py:31-49`), lui-même tiré de `signal_results`, vide depuis la purge du 08/10 : pas alimenté par les positions, donc pas contaminé (corrigé le 19/10, session 8 ; la v1 de ce tableau le disait contaminé) | — |
| Gains et pertes consécutifs | Modes DEFENSIF et AGRESSIF (`budget_manager/strategy.py:57`, `:91`, `:119`), porte paper à 9 (`paper_trader/portfolio.py:40-58`) | 07/05 |
| `lessons_learned.md`, `market_patterns.md` | Leçons écrites après 3 pertes, patterns après 3 occurrences : une seule boucle suffit. Un pattern trouvé ajoute ensuite +1 à l'intuition (`intuition.py:74-77`) | 07/05 |
| `contexte.winrate_actif` du registre | Même source que le winrate par actif (`utils/registre_cycles.py:102-103`) : vide, pas contaminé (corrigé le 19/10, session 8) | — |

**Le §4 du registre (« Prix de départ décalé ») sous-estime le décalage.** Ta demande le place au
§0.3 ; il est en fait au §4. Il ne parle que des cryptos (« relevé de 06h30 UTC »). En réalité :
- pour les actions et les ETF du tactical (73 % des BUY/SELL), p0 est la clôture de la séance
  précédente : 30,8 h en médiane, 49,5 h au 3e quartile ;
- en crypto, l'écart sans signe (1,8 % en médiane) est du même ordre que l'effet que Q1 cherche à
  détecter (environ 1,5 % à J+5 avec n = 125, §0.4) ;
- le registre ne mentionne pas les boucles du paper.

## 4. Options de correction, classées (non implémentées)

1. **Prix frais obligatoire à l'ouverture.**
   - Fonctionnement : à l'ouverture, demander le cours du moment (la même source que la
     surveillance) et recalculer le SL, le TP et la taille sur ce prix. Enregistrer ce prix et son
     heure à côté de p0. Si le cours est indisponible, ne pas ouvrir.
   - Effets : la décision BUY/SELL ne change pas. Le Risk Manager peut refuser davantage (R:R
     recalculé). Les boucles disparaissent, puisque l'écart d'entrée devient presque nul. Il faut un
     appel réseau par ouverture, soit quelques-uns par jour.
   - C'est l'option la plus proche d'un ordre réel.
2. **Âge maximal du prix**, par exemple 6 h, en refusant l'ouverture au-delà, plus un délai de carence
   après une fermeture.
   - Effets : c'est simple, mais presque aucune action ne s'ouvrirait plus pendant la séance (prix
     toujours de plus de 19 h). Les ouvertures se concentreraient au cycle quotidien. L'échantillon
     paper diminue, et p0 reste figé dans le registre.
3. **Ouvrir seulement juste après un rafraîchissement**, soit au cycle quotidien, soit en
   rafraîchissant les barres à chaque passage du tactical.
   - Effets : dans la première variante, le tactical n'ouvre plus rien. Dans la seconde, les
     indicateurs du tactical portent sur une barre en cours, donc les **décisions elles-mêmes**
     changent, et il faut 96 collectes par jour chez Yahoo, déjà en 429.

Quelle que soit l'option, un garde-fou anti-boucle (pas de réouverture du même actif au même prix
d'entrée) est utile. Toute correction rompt les séries paper : voir
`docs/BROUILLON_RUPTURE_PRIX_ENTREE.md`.

## 5. Ce que ce diagnostic ne dit pas

- Il ne dit pas si les boucles ont fermé au stop ou à l'objectif, ni ce qu'elles ont rapporté.
  Avant R2, l'âge n'est connu que pour 77 ouvertures sur 351.
- La docstring de `monitor.py:25-27` annonce une convention sur le plus bas du jour. Le code
  compare seulement le cours du moment.
