# Registre des décisions — critères de lecture pré-enregistrés

**Statut : v1 du 06/10/2026, commitée avant la première écriture du registre (R2).**
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
- **Composition changeante.** Les explorateurs ajoutent des actifs à la
  watchlist au fil du temps : on ne compare pas toujours les mêmes actifs d'un
  mois à l'autre.
- **Rupture de série du 06/10/2026** (TODO §11) : aucune donnée antérieure à P10
  n'est utilisée pour décider. Les volumes du §0.4 ne servent qu'à dimensionner.
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
