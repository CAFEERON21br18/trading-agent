# Registre des décisions — critères de lecture pré-enregistrés

**Statut : v1 du 06/10/2026, commitée avant la première écriture du registre (R2) ;
v1.1 du 06/10/2026 (décisions sans données exclues, §0.1), commitée avant toute
lecture.**
Toute modification ultérieure, y compris celle des coûts, fait l'objet d'un
nouveau commit daté. Elle ne s'applique qu'aux données enregistrées après ce
commit, et jamais après avoir regardé un résultat.

But : décider à l'avance ce qui sera mesuré, quand, et ce qu'on change selon le
résultat. On évite ainsi de chercher dans les données une règle qui « marche »
après coup.

---

## 0. Règles communes

### 0.1 Unité d'observation
- **Décision représentative.**
  - Question 1 : la décision du cycle quotidien de 07h30, soit une par actif et
    par jour (même heure et même pipeline pour tous les actifs).
  - Questions 2 et 3 : la première décision BUY ou SELL normale du jour qui est
    passée par le pipeline, ou qui aurait dû y passer, par couple
    (actif, jour, action). Le pipeline est mis en cache sur ce couple (Q2).
- **Groupes d'actifs corrélés**, chacun compté comme un seul actif :
  - `CRYPTO` : BTC-USD, ETH-USD, SOL-USD, HBAR-USD, CRO-USD ;
  - `INDICES_US` : SPY, QQQ, VOO, NQ=F ;
  - `SEMIS_IA` : NVDA, AMD, MU, AMAT, LITE, VRT, VST, CEG. C'est le second
    facteur commun du portefeuille.

  Les autres actifs (AAPL, AMZN, MSFT, TSLA, GC=F, CL=F, ainsi que tout actif
  ajouté plus tard par les explorateurs) sont comptés seuls, sauf s'ils sont
  ajoutés à un groupe par un nouveau commit de ce fichier.
- **Observation indépendante, selon l'horizon :**
  - J+1 : un couple (groupe, jour) ;
  - J+5 : un couple (groupe, semaine ISO) ;
  - J+10 : un couple (groupe, période de deux semaines).

  Les rendements de deux jours consécutifs se chevauchent à J+5 et J+10 : on ne
  les compte donc pas deux fois. Plusieurs actifs d'un même groupe dans un même
  bloc, ou plusieurs jours d'un même actif, sont moyennés en une seule observation.
- **Chaque résultat affiche son nombre d'observations indépendantes**, et le
  nombre de lignes du registre à titre d'information seulement.
- **Décisions sans données de prix : exclues** (v1.1). Une ligne `decision`
  dont l'analyse n'avait aucun prix n'est ni une observation, ni comptée dans
  un dénominateur, pour toutes les questions. Elle est reconnue :
  - depuis R2c, à `suite.resultat = "sans_donnees"` ;
  - pour toutes les lignes, y compris celles écrites avant R2c, à la colonne
    `prix` vide (c'est le même critère : le prix de l'analyse technique est
    absent).

  Raison : sans prix, les quatre sous-agents sont neutres et la décision
  (HOLD, score 0) est imposée par l'absence de données, pas prise ; le
  rendement ne peut pas non plus être calculé (pas de p0). Ces lignes sont
  comptées à part et le compte (lignes, tickers distincts) est affiché avec
  chaque résultat. Au 06/10/2026, ce sont les tickers de la queue des
  explorateurs (TODO §14).

### 0.2 Rendement mesuré
- **Prix de départ** p0 : le prix enregistré dans la ligne, c'est-à-dire la
  dernière clôture utilisée par la décision.
- **Prix d'arrivée** pJ+h : la clôture du h-ième jour de cotation suivant dans
  `prices` (jours calendaires pour les cryptos). Ces barres sont complètes
  depuis P10.
- **Rendement orienté** : (pJ+h / p0 − 1) pour un BUY, et son opposé pour un SELL.
- **Coûts aller-retour déduits :** 0,2 % hors crypto et 1,0 % pour les cryptos.
  Si tes frais Revolut réels sont plus élevés, les valeurs sont relevées par un
  commit de ce fichier **avant** la lecture concernée.

### 0.3 Méthode et discipline de lecture
- Moyenne et intervalle de confiance par bootstrap par blocs, avec 10 000 tirages
  sur les observations indépendantes.
- **Une seule lecture par question**, quand le nombre minimal d'observations est
  atteint ou à l'échéance. Avant cette lecture, seul le compteur d'observations
  est consulté, jamais un rendement : pas d'arrêt opportuniste.
- **Résultat mitigé = on ne change rien.** Si l'intervalle de confiance contient
  la frontière de décision, le paramètre reste tel quel. Pas de « presque
  significatif », pas de seconde lecture « pour voir ».
- **Échéance dépassée** sans le nombre minimal d'observations : la question est
  « non décidable » et rien ne change. Elle peut être reposée par un nouveau commit.
- Les horizons J+1 et J+10 restent **descriptifs** : seule la métrique primaire
  de chaque question peut déclencher un changement.

### 0.4 Volumes et délais attendus (estimation au 06/10/2026)
Source : les 42 rapports quotidiens du 25/08 au 06/10, soit 966 couples
(actif, jour) sur 23 actifs. Ce sont des données antérieures à P10 : les
volumes réels peuvent s'écarter d'environ 20 %. Avec les trois groupes, on
compte au plus 9 unités indépendantes par semaine (3 groupes et 6 actifs seuls).

| Tranche de score | Couples / semaine | Indépendants J+1 / sem. | Indépendants J+5 / sem. | Indépendants J+10 / sem. |
|---|---|---|---|---|
| ≥ 3.0 | 6,0 | 4,0 | 1,7 | 1,3 |
| **2.0 – 3.0** | **45,5** | 23,7 | **5,3** | 3,3 |
| 0.5 – 2.0 (apprentissage) | 12,7 | 10,0 | **3,5** | 2,5 |
| −0.5 – 0.5 (neutre) | 83,7 | 41,8 | 8,8 | 5,0 |
| −2.0 – −0.5 (apprentissage) | 3,2 | 3,2 | 1,5 | 1,2 |
| ≤ −2.0 | 10,0 | 7,7 | 2,5 | 2,2 |

Décisions examinées par le pipeline (logs du tactical, du 22/09 au 06/10) :
environ 36 couples (actif, jour) par semaine, soit **5,5 observations
indépendantes J+5 par semaine**.

Écart-type des rendements à J+h (barres journalières du 01/04 au 06/10, médiane par classe) :

| Classe | J+1 | J+5 | J+10 |
|---|---|---|---|
| Cryptos | 2,8 % | 6,7 % | 9,8 % |
| Actions | 2,9 % | 6,6 % | 8,7 % |
| Indices US | 1,0 % | 2,3 % | 3,1 % |

**Taille nécessaire.** Pour détecter un rendement moyen δ différent de zéro
(seuil de 5 % bilatéral, puissance de 80 %), il faut n ≈ (2,8 × σ / δ)². Avec
σ ≈ 6 % à J+5, n = 125 permet de détecter un effet d'environ 1,5 %.

**Délais**, comptés à partir de la mise en service de R2 :

| Lecture | n | Rythme | Durée estimée | Échéance (2 × durée) |
|---|---|---|---|---|
| Q1, seuil BUY (tranche 2.0–3.0) | 125 | 5,3 / sem. | ≈ 23 semaines | 46 semaines |
| Q1, zone d'apprentissage (0.5–2.0) | 125 | 3,5 / sem. | ≈ 36 semaines | 72 semaines |
| Q3.a, verdicts non informatifs | 40 couples examinés | ≈ 36 / sem. | lecture fixée à 4 semaines | 8 semaines |
| Q3.b, rendement des décisions examinées | 125 | 5,5 / sem. | ≈ 23 semaines (lu avec Q1) | 46 semaines |
| Q2, mode Prudent | 35 par groupe | inconnu (replis rares depuis Q4) | — | 16 semaines |

---

## 1. Seuil BUY (`SEUIL_BUY` = 2.0)

**Question.** Les décisions BUY normales de la tranche [2.0 ; 3.0[ ont-elles un
rendement positif ? Si elles perdent, le seuil est trop bas.

**Métrique primaire.** Rendement orienté à J+5, net de coûts, moyenné sur les
observations indépendantes (groupe, semaine) de la tranche [2.0 ; 3.0[.
La tranche ≥ 3.0 est trop rare (environ 1,7 observation indépendante par
semaine) pour servir de point de comparaison : on teste la tranche contre zéro.

**Nombre minimal d'observations** : n = 125, soit environ 23 semaines ;
échéance à 46 semaines.

**Règle de décision (D1).** `SEUIL_BUY` passe à 3.0 si la borne haute de l'IC à
95 % est inférieure à 0, c'est-à-dire si la tranche perd nettement. Sinon, 2.0
est conservé. **Un résultat mitigé ne change rien.**

**Seuil SELL** (tranche ]−3.0 ; −2.0]) : environ 2,5 observations
indépendantes par semaine, soit environ 28 semaines même pour n = 70.
**Non évalué : `SEUIL_SELL` reste à −2.0.**

**Zone d'apprentissage [0.5 ; 2.0[** (micro-positions), évaluée :
- même métrique, n = 125, environ 36 semaines, échéance à 72 semaines ;
- règle : les trades d'apprentissage sont arrêtés (taille 0) si la borne haute
  de l'IC à 95 % est inférieure à 0. Sinon, rien ne change.

---

## 2. Mode Prudent (`PIPELINE_FALLBACK_FACTOR` = 0.5)

**Question.** Quand le pipeline échoue, sans résultat en cache, les décisions
sont-elles moins bonnes que quand il réussit ?

**Constat préalable.** Le 06/10, avant Q4 : 5 replis pour 3 couples distincts.
Depuis Q4, le pipeline passe directement par Groq et les replis devraient être
rares.

**Règle retenue (P3) : suivi seulement.** La fréquence des replis (par jour, par
heure et par fournisseur LLM) est publiée chaque semaine. Le rendement des
décisions en mode Prudent (n = 35 par groupe, échéance 16 semaines) est
**descriptif** : il ne déclenche aucun changement. Le facteur 0.5 reste un choix
de conception.

---

## 3. Réductions du pipeline (pré-mortem, métacognition, base rates)

**Fonctionnement actuel** (`agents/skills/pipeline_grouped.py`) : un seul appel
LLM groupé produit cinq analyses. Trois verdicts réduisent la taille, en se
multipliant :
- « Pré-mortem ALERTE » : ×0,5 ;
- « Métacognition FRAGILE » : ×0,5 ;
- « Base rates ALERTE » : ×0,7.

Les deux autres analyses (bayésienne, second ordre) ne servent qu'au rapport.
Du pipeline, le Decision Engine n'utilise que le facteur de taille.

**Constat préalable** (logs du tactical, depuis le 22/09) : sur 72 couples
(actif, jour) examinés, **68 (94 %) ont reçu ×0,17**, avec les trois verdicts
réducteurs à la fois. Un verdict presque toujours identique ne distingue rien :
on ne peut pas tester s'il « prédit » un mauvais trade.

### 3.a — Critère structurel (sans rendement), lu à 4 semaines
Pour chaque verdict réducteur, si la même valeur apparaît dans au moins 90 % des
couples examinés (n ≥ 40), le verdict est déclaré **non informatif**. Il est
alors **remplacé par un facteur fixe égal à sa moyenne observée** sur la
période. Exemple : un « Pré-mortem ALERTE » présent dans 94 % des cas donne
0,94 × 0,5 + 0,06 × 1 = 0,53. La taille moyenne ne change pas ; le verdict n'est
simplement plus demandé au LLM.
- Si **les trois** verdicts réducteurs sont remplacés, l'appel LLM groupé n'a
  plus d'effet sur aucune décision. Il peut être supprimé, ce qui fera perdre au
  rapport les textes bayésien et de second ordre (étape d'implémentation
  séparée, avec diff et test).
- Si un ou deux verdicts seulement sont remplacés, l'appel groupé subsiste, car
  c'est un seul appel pour les cinq analyses : on ne gagne aucun appel.
- **Changer le niveau de risque global**, par exemple supprimer la réduction
  moyenne, reste une décision séparée, hors de ce critère.

### 3.b — Critère de rendement, lu avec la question 1
Métrique : rendement orienté moyen à J+5, net de coûts, des décisions examinées
par le pipeline (observations indépendantes (groupe, semaine)), avec n = 125,
soit environ 23 semaines, et une échéance à 46 semaines.
- Si la borne basse de l'IC à 95 % est supérieure à 0 : ces décisions gagnent,
  donc la réduction coûte de l'argent. **Le produit des facteurs du pipeline est
  alors plafonné à ×0,5**, au lieu de ×0,17, que ces facteurs viennent du LLM
  ou de 3.a.
- Si la borne haute de l'IC à 95 % est inférieure à 0 : les réductions sont
  conservées ; voir la question 1.
- Résultat mitigé : rien ne change.

⚠️ **3.b et la question 1 portent en grande partie sur les mêmes décisions**
(BUY normaux de la tranche 2.0–3.0). Elles sont lues ensemble, à la même date,
et leurs conclusions doivent être cohérentes. Si Q1 conduit à relever le seuil,
3.b ne s'applique pas en même temps.

**Mesure descriptive** : la part des BUY refusés par le Budget Manager parce que
la taille réduite tombe sous le minimum viable de 15 €.

---

## 4. Ce que le registre ne peut pas dire

- **Une seule période de marché.** Les données couvrent quelques mois d'un même
  régime. Un seuil validé à l'automne 2026 peut ne plus convenir dans un marché
  différent : un résultat n'est pas une loi.
- **Des actifs corrélés au-delà des groupes.** Même avec trois groupes, toutes
  les actions bougent ensemble avec le marché. Une journée de hausse générale
  fait « gagner » toutes les décisions BUY à la fois. Le nombre réel
  d'observations indépendantes reste donc inférieur au compte affiché.
- **Peu de trades réels.** Avec 0 ou 1 ouverture par jour, le P&L réalisé
  restera un très petit échantillon. Le registre évalue des **décisions**
  d'après l'évolution du prix, pas des trades exécutés. Ne sont pas mesurés :
  le moment réel d'entrée, le glissement, les frais réels, ni les sorties
  anticipées.
- **Pas d'ordre à l'intérieur d'une journée.** Avec des barres journalières, si
  le stop et l'objectif sont touchés le même jour, on ne sait pas lequel l'a été
  en premier.
- **Prix de départ décalé.** p0 est la dernière clôture en base ; pour les
  cryptos, c'est le relevé de 06h30 UTC, pas un prix exécutable au moment de la
  décision.
- **Composition changeante.** La watchlist peut être modifiée depuis le
  dashboard (correction v1.1 : les explorateurs ne l'élargissent pas, ils
  alimentent la queue) : on ne compare pas toujours les mêmes actifs d'un mois
  à l'autre. La composition entrera dans l'empreinte des paramètres en R3
  (TODO §13).
- **Rien sur les découvertes des explorateurs.** Tant que les actifs de la
  queue n'ont pas de prix (TODO §14), leurs décisions sont exclues (§0.1) : le
  registre ne dit pas si les explorateurs trouvent de bonnes opportunités.
- **Rupture de série du 06/10/2026** (TODO §11) : aucune donnée antérieure à P10
  n'est utilisée pour décider. Les volumes du §0.4 ne servent qu'à dimensionner.
- **Statistiques de performance fictives du 06/10/2026 à la purge du
  08/10/2026** (TODO §24) : les décisions enregistrées jusque-là ont lu les
  winrates de la démo du 15/04 (`contexte.winrate_actif` = 100.0 sur BTC-USD
  et AAPL, 0.0 sur ETH-USD ; prior 0,67 dans le pipeline). 0 décision et
  0 allocation changées ; l'effet sur les verdicts du pipeline (§3) n'est pas
  mesurable.
- **Pas de lien de cause à effet sur les LLM.** Un verdict constant ne permet
  pas de dire si le LLM « a raison » : seulement qu'il ne trie pas.
- **Paper ≠ réel.** Aucune conclusion ne s'applique automatiquement au
  portefeuille réel.

---

## 5. Choix retenus (v1)

| # | Choix retenu | Options écartées |
|---|---|---|
| 0.1 | Groupes `CRYPTO`, `INDICES_US` et `SEMIS_IA` | cryptos seules |
| 0.2 | Coûts : 0,2 % hors crypto, 1,0 % crypto | 0,2 % partout ; aucun coût |
| 1 | n = 125 ; règle D1 (3.0 si la borne haute de l'IC à 95 % est < 0) ; zone d'apprentissage évaluée | n = 70 ou 280 ; D2, D3 |
| 2 | P3 : suivi seulement (n = 35 par groupe, descriptif) | P1 (facteur 1.0) ; P2 (facteur 0) |
| 3.a | Verdict non informatif remplacé par un facteur fixe égal à sa moyenne observée | R1 (désactiver la réduction) ; R2 (noter seulement) ; R3 |
| 3.b | Produit des facteurs plafonné à ×0,5 | suppression des réductions |

## 6. Versions
- v0, 06/10/2026 : brouillon avec options.
- v1, 06/10/2026 : options retenues, volumes et délais recalculés avec les trois
  groupes. Commitée avant R2.
- v1.1, 06/10/2026 : décisions sans données de prix exclues de toutes les
  questions (§0.1, marquage R2c) ; §4 corrigé (la watchlist n'est modifiée que
  depuis le dashboard) et complété (découvertes des explorateurs). Commitée
  avant toute lecture : le registre n'a fait l'objet que du contrôle technique
  de R2 (15 lignes, aucun rendement calculé).
- v1.2, 08/10/2026 : ajout du §7 (observation Jev, TypeSafe) : hypothèse,
  coûts par groupe, contrôle de lecture du régime, n = 40 unités, bootstrap par
  grappes de semaine ISO, règles d'arrêt et d'interruption. Commitée avant le
  premier `JEV_OBSERVE=1`, donc avant toute observation.
- v1.3, 08/10/2026 : §4 complété (statistiques de performance fictives jusqu'à
  la purge des signaux de démo, TODO §24). Aucune règle de lecture modifiée.
- v1.4, 08/10/2026 : ajout du §8 (portefeuille fantôme Jev, descriptif) et de
  sa seule exception à l'interdiction d'afficher un rendement avant la lecture
  (§0.3, §7.2). Aucun critère ni aucune règle de lecture modifiés. Commitée
  avant la première observation Jev, avant toute écriture du fantôme et avant
  tout affichage de son P&L.
- v1.5, 09/10/2026 : exception du §8.3 remplacée : la ligne du dashboard devient
  une page détaillée du fantôme (positions, P&L par position, historique,
  observations du jour). Fuite élargie, acceptée en connaissance de cause.
  Aucun critère ni aucune règle de lecture du §7 modifiés ; règles simulées du
  §8.2 inchangées. Commitée après la première observation Jev (09/10/2026,
  23 lignes) et les 6 premières entrées du fantôme, avant tout code de la page.

---

## 7. Observation Jev (TypeSafe) : ce que Jev doit prédire avant toute entrée dans le vote

**Statut : v1.2 du 08/10/2026, commitée avant le premier `JEV_OBSERVE=1`.**

**Ce qui est observé.** Chaque matin, au cycle quotidien de 07h30 (jamais le
tactical ni un lancement manuel), Jev reçoit pour chacun des 23 actifs le state
que reçoit le moteur : liste blanche de `agents/jev/state.py`, plus
`position_paper_ouverte`. Le modèle est figé (`jev-1.13.0`), les questions aussi
(v1, `agents/jev/questions.py`). La réponse de Jev n'entre dans aucune décision.
La décision du moteur est enregistrée dans la même ligne, sans être envoyée.

**Hypothèse testée.** Quand Jev répond « acheter » avec p(acheter) ≥ 0,6 sur un
actif sans position paper ouverte, le rendement acheteur à J+5, net de coûts,
est positif et supérieur à celui des actifs pour lesquels il ne le dit pas.

### 7.1 Observations
- Lignes `jev_observations` du cycle `quotidien`, statut `ok`, questions `v1`,
  modèle `jev-1.13.0` ; la première du jour par actif.
- Le critère ne porte que sur les observations **sans position paper ouverte**.
  Les autres sont affichées à part, en descriptif.
- Classes, sur ces mêmes observations :
  - **Jev-acheter** : p(acheter) ≥ 0,6 ;
  - **Jev-ne-rien-faire** : p(acheter) < 0,6 ;
  - **Moteur BUY** : décision BUY du moteur (normal ou apprentissage).
- Rendement : §0.2, orienté acheteur pour les trois classes (on compare
  « acheter ces actifs-là »). p0 = prix de la ligne ; pJ+5 = clôture de la 5e
  barre journalière datée du jour de l'observation ou après (la barre du jour
  clôt après 07h30).
- **Coûts aller-retour déduits, fixés ici :**

  | Groupe | Coût aller-retour |
  |---|---|
  | `CRYPTO` | 1,0 % |
  | `INDICES_US` | 0,2 % |
  | `SEMIS_IA` | 0,2 % |
  | Actifs seuls (AAPL, AMZN, MSFT, TSLA, GC=F, CL=F) | 0,2 % |

  Origine : ce sont les hypothèses du §0.2, retenues en v1 (§5, ligne 0.2) le
  06/10/2026. Ce sont des **hypothèses**, pas des frais Revolut mesurés : le
  calcul du coût net réel n'existe pas encore. Ne sont pas comptés : l'écart
  achat-vente réel, les frais de financement overnight (GC=F, CL=F et NQ=F
  sont traités en CFD sur Revolut) et le change EUR/USD. Comme au §0.2, ces
  valeurs ne peuvent être relevées que par un commit de ce paragraphe
  **avant** la lecture.
- **Unité indépendante** : §0.1, couple (groupe, semaine ISO) à J+5 ; les
  observations d'un couple sont moyennées, séparément dans chaque classe.

### 7.2 Calendrier, contrôle de lecture et lecture unique
- Fenêtre de collecte : **12 semaines** à partir de la première observation
  retenue. Les observations postérieures ne comptent pas.
- **Lecture unique** : fin de fenêtre + 10 jours, pour que le J+5 de la
  dernière observation existe.
- Avant cette date, `scripts/jev_bilan.py` n'affiche que des compteurs (lignes,
  erreurs par type, actifs écartés, observations, unités Jev-acheter) et le
  contrôle de lecture du régime. Aucun rendement.
- **Contrôle de lecture du régime** (affiché dès le départ, ce n'est pas un
  critère) : taux d'accord entre le régime de Jev et `context.regime_marche`,
  sur les observations dont le régime du moteur est l'un des quatre libellés.
  - Il est jugé sur les **10 premiers jours de bourse** observés (lundi à
    vendredi ; les observations crypto du week-end comptent, sans compter
    comme jours).
  - **Accord < 50 % : le test est arrêté.** On coupe `JEV_OBSERVE`, on corrige
    les questions ou le state, et la fenêtre repart de zéro sous une nouvelle
    version (questions v2), par un nouveau commit de ce paragraphe.
  - **Aucune correction en cours de fenêtre**, que l'accord soit bon ou mauvais.

### 7.3 Nombre minimal : 40 unités indépendantes Jev-acheter
- **Groupes utilisés** (§0.1) :
  - `CRYPTO` : BTC-USD, ETH-USD, SOL-USD, HBAR-USD, CRO-USD ;
  - `INDICES_US` : SPY, QQQ, VOO, NQ=F ;
  - `SEMIS_IA` : NVDA, AMD, MU, AMAT, LITE, VRT, VST, CEG ;
  - comptés seuls : AAPL, AMZN, MSFT, TSLA, GC=F, CL=F.

  Cela couvre les 23 actifs (5 + 4 + 8 + 6). Un actif ajouté plus tard compte
  seul (§0.1).
- **Maximum : 108 unités.** 3 groupes + 6 actifs seuls = 9 unités par semaine
  ISO, et 9 × 12 semaines = 108. Ce maximum suppose que Jev dise « acheter »
  chaque semaine dans chaque groupe. 40 demande donc qu'il le dise dans environ
  un couple (groupe, semaine) sur trois.
- **Puissance.** Avec σ ≈ 6 % à J+5, n ≈ (2,8 × σ / δ)² donne δ ≈ 2,7 % pour
  n = 40. Avec 40 unités, seul un effet ≥ ~2,7 % à J+5 est détectable.
  **Critère non atteint ≠ preuve d'absence d'effet** : on conclut seulement à
  l'absence d'effet massif.
- Sous 40 à la lecture : **non concluant**. Le seuil de 0,6 n'est pas baissé et
  la fenêtre n'est pas prolongée. La question ne peut être reposée que par un
  nouveau commit, avec une nouvelle fenêtre et de nouvelles observations.

### 7.4 Règle de décision
**Métrique primaire** : moyenne des unités Jev-acheter.

**IC à 95 % par bootstrap par grappes de semaine ISO.** Les unités d'une même
semaine ne sont pas indépendantes : le même marché les fait bouger ensemble.
- On tire avec remise autant de semaines qu'il y en a, et on garde toutes les
  unités de chaque semaine tirée. On fait **10 000 tirages** et on prend les
  percentiles 2,5 et 97,5.
- Graines fixes : 7001 (moyennes), 7002 (écart Jev-acheter − Jev-ne-rien-faire),
  7003 (écart Jev-acheter − moteur BUY).
- Pour un écart, les mêmes semaines sont tirées pour les deux classes
  (appariement par semaine). Un tirage sans unité dans l'une des deux classes
  est ignoré.
- Avec moins de 2 semaines, il n'y a pas d'IC, et la condition correspondante
  n'est pas remplie.

Le critère est **atteint** si les trois conditions sont réunies :
1. borne basse de l'IC à 95 % de la moyenne Jev-acheter > 0 ;
2. borne basse de l'IC à 95 % de l'écart Jev-acheter − Jev-ne-rien-faire > 0 ;
3. moins de 80 % des observations Jev-acheter sont aussi des BUY du moteur.
   Sinon, Jev est **redondant** avec le moteur.

Conséquences :
- **Atteint** : autorise seulement à rédiger un second critère (comment Jev
  entrerait dans le vote, avec quel poids, mesuré comment), par un nouveau
  commit. Rien n'entre automatiquement dans le vote.
- **Redondant, non atteint ou mitigé** : rien ne change. Jev reste hors du
  vote ; l'observation peut être coupée.

### 7.5 Descriptif, jamais un critère
- Écart Jev-acheter − moteur BUY (IC affiché, sans règle) ;
- résultats par groupe, et par actif et par jour (« descriptif, pas un
  critère ») ;
- observations avec position ouverte, par action de Jev ;
- conviction et taille hypothétique (jamais exécutée), latence, erreurs,
  actifs écartés, jetons.

### 7.6 Gel pendant la fenêtre
Sont figés pour toute la fenêtre :
- les questions (textes, et ordre des options `ne_rien_faire`, `conserver`,
  `acheter`) ;
- le modèle `jev-1.13.0` ;
- la liste blanche du state ;
- le timeout de 3 s et le budget de 120 s ;
- l'ordre des actifs, tiré au sort avec la date comme graine.

Toute modification passe par un nouveau commit daté de ce paragraphe et ouvre
une nouvelle fenêtre ; les observations de deux versions ne se mélangent pas.

**Si `jev-1.13.0` n'est plus servi pendant la fenêtre**, le test est
**interrompu**. Ce cas se voit dans les erreurs par type du bilan, et se
confirme avec la liste des modèles de TypeSafe.
- On coupe `JEV_OBSERVE` et **on ne change pas de version**.
- Les observations déjà faites ne sont pas lues.
- Une nouvelle fenêtre ne peut s'ouvrir que sous un **nouveau critère**, par un
  nouveau commit.

### 7.7 Ce que ce critère ne peut pas dire
- Jev lit mal les nombres (documentation de jev-1.13), et le state est surtout
  numérique : un échec peut venir du format du state, pas du modèle.
- Jev favorise la première option ; ici, ce biais joue contre « acheter ».
- Une seule période de 12 semaines ; actifs corrélés au-delà des groupes (§4).
- Coûts supposés, pas mesurés (§7.1).
- Les jours où le cycle quotidien échoue ne sont pas observés.
- Paper ≠ réel : aucune conclusion ne s'applique au portefeuille réel.

---

## 8. Portefeuille fantôme Jev : descriptif, jamais un critère

**Statut : v1.4 du 08/10/2026, commitée avant la première observation Jev,
avant toute écriture dans les tables du fantôme et avant tout affichage de son
P&L. v1.5 du 09/10/2026 : §8.3 remplacé (page détaillée), commitée après la
première observation Jev et les premières entrées du fantôme, avant tout code
de cette page.**

**Le portefeuille fantôme Jev est descriptif ; son P&L n'est ni un critère ni
une raison de modifier le §7 ; aucune décision ne se prend sur sa base avant la
lecture unique.** Ce n'est pas non plus une raison d'arrêter l'observation :
avant la lecture, seuls le contrôle de lecture du régime (§7.2) et
l'interruption du modèle (§7.6) l'arrêtent.

But : voir en euros, à côté du paper actuel, ce qu'aurait donné le fait de
suivre les « acheter » de Jev, sans rien changer au paper, au moteur ni au
critère du §7.

### 8.1 Isolation
- Deux tables séparées, `jev_paper_positions` et `jev_paper_journal`. Elles ne
  sont lues ni par le moteur, ni par le Budget Manager, ni par le Paper Trader,
  ni par le registre, ni par les lectures des questions 1 à 3, ni par le bilan
  du §7 (`scripts/jev_bilan.py`).
- Le fantôme n'écrit dans aucune table du paper (`positions`, `transactions`,
  `portfolio_snapshots`) ni dans `memory/`. Il ne les lit pas non plus : l'état
  du paper qu'il utilise est celui figé dans l'observation (`position_ouverte`,
  `mode_bm`).
- Aucun nouvel appel à Jev ni à une source de prix : il réutilise les lignes
  `jev_observations` et la table `prices`.

### 8.2 Règles simulées
- **Observations utilisées** : celles du §7.1 (cycle `quotidien`, statut `ok`,
  questions `v1`, modèle `jev-1.13.0`, première du jour par actif). Le fantôme
  continue après la fenêtre de 12 semaines tant que des observations arrivent ;
  ces observations postérieures restent hors du critère du §7. Une autre version
  des questions ou du modèle ne l'alimente qu'après un nouveau commit de ce
  paragraphe.
- **Capital de départ** : `CAPITAL` (1 000 €), comme le paper.
- **Entrée** (achat seulement) si les trois conditions sont réunies :
  1. p(acheter) ≥ 0,6 ;
  2. pas de position paper ouverte sur l'actif, d'après `position_ouverte` figée
     dans l'observation (même population que le critère du §7.1) ;
  3. aucune position fantôme ouverte sur l'actif.
- **Prix d'entrée** : le prix de la ligne (p0 du §7.1), sans nouvel appel.
- **Taille** : facteur de conviction (0 ; 0,2 ; 0,5 ; 1,0, voir
  `agents/jev/questions.py`) × `montant_risque` (montant du Risk Manager figé
  dans l'observation), plafonnée comme le paper, sur l'état du fantôme :
  - au plus le maximum par trade du mode du Budget Manager figé dans
    l'observation (`mode_bm` ; 10 % en NORMAL), appliqué au cash libre du
    fantôme ;
  - au plus le cash libre du fantôme : capital investissable du mode (500 € en
    NORMAL, soit 50 % de `CAPITAL`) moins le montant investi dans les positions
    fantômes ouvertes ;
  - au plus `MAX_POSITIONS_SIMULTANEES` positions fantômes ouvertes (20 dans
    `.env`) ;
  - pas d'achat sous 15 € (minimum viable du Budget Manager).

  Dans une même journée, les candidats sont traités par p(acheter) décroissant,
  puis par ticker.
- **Journal** : chaque entrée, chaque sortie, et chaque observation avec
  p(acheter) ≥ 0,6 non achetée, avec son motif :

  | Motif | Cas |
  |---|---|
  | `conviction_nulle` | niveau de conviction 0 |
  | `sans_montant_risque` | `montant_risque` vide (technique neutre : Risk Manager non appelé) |
  | `montant_vente_a_decouvert` | montant calculé pour une vente à découvert (signal du Risk Manager en SHORT) |
  | `sans_prix` | prix de la ligne absent |
  | `sans_mode_bm` | mode du Budget Manager absent de l'observation |
  | `position_paper_ouverte` | condition 2 non remplie |
  | `position_fantome_ouverte` | condition 3 non remplie |
  | `max_positions` | nombre maximal de positions fantômes atteint |
  | `sous_minimum` | taille plafonnée inférieure à 15 € |

- **Sortie** : à la clôture de la 5e barre journalière de `prices` datée du jour
  de l'observation ou après, soit l'horizon J+5 du §7.1.
  - Les week-ends et jours fériés suivent les barres : un jour férié US sans
    barre ne compte pas ; une barre de future un jour férié US compte, comme au
    §7.1 ; les cryptos sont en jours calendaires.
  - La sortie est passée au premier cycle quotidien où cette barre est datée
    d'avant le jour du cycle (barre close). Le prix de sortie ne dépend pas de
    ce délai.
  - Les sorties d'un jour sont passées avant ses entrées.
  - Ni stop, ni objectif, ni vente décidée par Jev.
- **Coûts aller-retour**, déduits à la sortie sur le montant investi : ceux du
  §7.1 (1,0 % `CRYPTO`, 0,2 % pour le reste).

### 8.3 Exception au §0.3 et au §7.2 : affichage avant la lecture
Le §0.3 et le §7.2 interdisent de consulter un rendement avant la lecture
unique. **Seule exception** (v1.5, remplace celle de v1.4) : la ligne de
comparaison de la page d'accueil du dashboard et une page détaillée « Fantôme
Jev ». Les deux sont en lecture seule (base ouverte en `mode=ro`, aucune
écriture) et portent la mention visible « descriptif, pas un critère — lecture
le 11/01/2027 ». La page détaillée est autorisée à montrer :
- **les positions** fantômes ouvertes : actif, groupe, date d'entrée,
  p(acheter), niveau de conviction, montant investi, prix d'entrée, dernière
  clôture de `prices`, P&L latent en € et en %, date de sortie prévue (5e barre,
  §8.2) ;
- **le P&L par position** et **l'historique** : les positions fermées, avec leur
  P&L net des coûts du §7.1 (€ et %) et leur total cumulé ;
- **les observations du jour** : pour chaque actif de la dernière observation,
  la réponse de Jev (choix, p(acheter), conviction, régime), le régime et la
  décision du moteur, et ce qu'a fait le fantôme (achat, ou refus avec son
  motif du §8.2) ;
- **la comparaison avec le paper** : valeur de chacun et nombre de positions
  ouvertes, nombre de refus par motif. Même fenêtre des deux côtés : depuis la
  première entrée du fantôme (côté paper : positions ouvertes à partir de ce
  jour). Valeur = 1 000 € + P&L réalisé + P&L latent à la dernière clôture de
  `prices`, coûts du §7.1 déduits des deux côtés. Côté paper, ces coûts ne sont
  appliqués que pour cet affichage : ses tables ne changent pas.

Un prix manquant s'affiche « non disponible », jamais 0. Le P&L n'a pas de
couleur de gain ou de perte.

L'exception s'arrête là : `scripts/jev_bilan.py` reste aux compteurs. Aucune
métrique du §7 n'est affichée avant la lecture : ni rendement des observations
non achetées (Jev-ne-rien-faire, refus du fantôme), ni rendement des BUY du
moteur, ni moyenne par groupe, par classe ou par unité (groupe, semaine), ni
intervalle de confiance. Les seuls rendements montrés sont ceux des positions
du fantôme, une par une, et leur total.

**Fuite élargie, acceptée en connaissance de cause.** Le critère du §7 reste
figé ; rien de ce que montre cette page ne peut motiver avant la lecture du
11/01/2027 : un changement du §7 ou du §8, l'arrêt de l'observation (seuls §7.2
et §7.6 l'arrêtent), ni une intégration de Jev au vote.

Ce qui fuit : les positions du fantôme sont des observations Jev-acheter tenues
jusqu'au J+5 du §7.1. Leur P&L, position par position, laisse voir avant la
lecture une grande partie de la métrique primaire du §7, à la taille et aux
plafonds près. La date du 11/01/2027 est celle du §7.2 : première observation
retenue le 09/10/2026, plus 12 semaines, plus 10 jours.

### 8.4 Ce que le fantôme ne peut pas dire
- Ce n'est pas le critère du §7 : la taille selon la conviction, les plafonds et
  l'ordre de traitement font que tous les Jev-acheter ne sont pas achetés, ni
  avec le même poids.
- La comparaison avec le paper n'est pas à armes égales : le paper a des stops
  et des objectifs, des ventes à découvert, des durées variables et les
  décisions du moteur.
- Peu de positions : au plus une par actif et par période de cinq barres.
- Mêmes limites que le §4 et le §7.7. Paper ≠ réel.
