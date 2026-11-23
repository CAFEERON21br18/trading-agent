# Horizons d'investissement : proposition à valider (19/10/2026)

**Statut : proposition.** Rien n'est branché. Ce document part de tes 5 horizons et dit,
pour chacun, ce que le système fait déjà, les données disponibles, le poids des coûts et
ce qui manque. Il ne contient aucun rendement de décision, de signal, de Jev ou du fantôme.

## 1. Tes 5 horizons et ce qui existe

| Ton horizon | Durée | Ce qui s'en rapproche aujourd'hui |
|---|---|---|
| Long terme | 5 à 10 ans | rien de distinct (le plan « Long Terme » s'arrête à 5 ans) |
| Moyen terme | 1 à 3 ans | plan réel « Long Terme » (`seed_plans.py` : « 2-5 ans ») |
| Court terme | 3 à 8 mois | plan réel « Moyen Terme » (« semaines à quelques mois ») |
| Très court terme | 1 semaine à 1 mois | paper trading, registre à J+1/J+5/J+10, fantôme Jev à J+5, poche `trades_quotidiens_paris` (25 % du Moyen Terme) |
| « Galactique » | secondes à heures | plan réel « Court Terme » (« heures à jours »), cycles de 5 et 15 minutes |

Les libellés de `scripts/seed_plans.py` (modèle commité) ne suivent donc pas tes 5 types :
chaque nom y désigne un horizon plus court que le tien. Les plans réels de la base
(`investment_plans`) ne sont pas touchés par ce document.

**Ce que font les cycles**, quel que soit l'horizon :
- 5 min (critique) : SL/TP des positions paper, au cours du moment (`yfinance`, `period="1d"`) ;
- 15 min (tactique) : décisions sur la watchlist et la queue, à partir des barres journalières ;
- 4 h (stratégique) : conseils sur les positions réelles. `agents/real_advisor_rules.py`
  adapte le conseil au type de plan : patience entre −15 % et −25 % en Long Terme,
  « couper rapidement » en Court Terme, signal SELL atténué en Long Terme ;
- quotidien (7h30) : collecte des barres, rapport, rotation en observation.

## 2. Données disponibles (base `prices`, 19/10)

| Données | Actifs | Profondeur | Mise à jour |
|---|---|---|---|
| Barres 1d | 23 (watchlist) | 584 à 921 barres, depuis 04/2024 | une fois par jour, cycle quotidien |
| Barres 1wk | 23 | 248 à 289 barres, depuis 04/2021 (5 ans) | une fois par jour |
| Barres « 4h » (en fait des barres 1 h) | 5 cryptos | 4 314 à 5 982 barres, depuis 02/2026 | une fois par jour |
| Cours du moment | tout ticker | dernier cours Yahoo (`period="1d"`) | à chaque contrôle |
| Fondamentaux | 5 actions US (`ACTIONS_US`) + cryptos (CoinGecko) | ratios du jour seulement, pas d'historique | Alpha Vantage, 25 appels/jour (docs/CONSOMMATION_API.md) |
| Résultats des signaux | — | `signal_results` vide (0 ligne) | — |

Il n'y a ni barres à la minute, ni carnet d'ordres, ni spread mesuré. Les 7 autres actions
de la watchlist n'ont aucun fondamental.

## 3. Ce que les coûts mangent, par horizon

Amplitude médiane d'un mouvement de marché (valeur absolue, médiane par actif puis entre
actifs, barres de `prices`). C'est la volatilité des actifs, pas le résultat d'une stratégie.
Coûts aller-retour : ceux du registre (§0.2), 1,0 % pour les cryptos et 0,2 % hors crypto.
Ce sont des estimations, tes frais Revolut réels ne sont pas encore mesurés.

| Horizon | Mouvement médian crypto | Mouvement médian hors crypto | Coûts / mouvement crypto | Coûts / mouvement hors crypto |
|---|---|---|---|---|
| 1 heure | 0,28 % | pas de données | 357 % | — |
| 4 heures | 0,56 % | pas de données | 179 % | — |
| 1 jour | 1,89 % | 1,55 % | 53 % | 13 % |
| 1 semaine (5 barres) | 4,58 % | 3,64 % | 22 % | 5 % |
| 1 mois (4 semaines) | 12,97 % | 6,39 % | 8 % | 3 % |
| 6 mois | 39,5 % | 18,9 % | 2,5 % | 1,1 % |
| 1 an | 53,0 % | 27,2 % | 1,9 % | 0,7 % |
| 3 ans | 70,6 % | 82,7 % | 1,4 % | 0,2 % |

Sous une journée, les coûts dépassent le mouvement typique. Au-delà d'un mois, ils
deviennent secondaires. Les lignes à 3 ans reposent sur 5 ans de barres : les fenêtres se
chevauchent, et il y a très peu d'observations indépendantes.

## 4. Horizon par horizon

### « Galactique » (secondes à heures) : pas réaliste aujourd'hui
- **Déjà là :** les cycles de 5 et 15 minutes. Aucune décision n'est prise sur des barres intrajournalières.
- **Données :** des barres 1 h pour 5 cryptos seulement, collectées une fois par jour.
  Il n'y a ni minute ni tick. Les cycles du planificateur Windows tournent au mieux toutes
  les 5 minutes.
- **Coûts :** 1,8 à 3,6 fois le mouvement typique d'une à quatre heures (crypto).
- **Exécution :** Revolut sans API, donc un ordre passé à la main, avec des minutes de délai au mieux.
- **Constat lié :** le paper se comporte déjà ainsi, sans l'avoir voulu. 315 des 418
  positions paper fermées ont duré moins d'une heure ; en octobre, 68 fermées avec une durée
  médiane de 0,1 h. Le prix d'entrée était alors la dernière barre de `prices`, collectée une fois
  par jour (corrigé depuis : prix frais de moins de 15 min à l'ouverture et anti-boucle de 24 h,
  registre v1.8 §9.4) : sur les 69 ouvertures du registre depuis le 06/10, cette barre a 46 h en médiane
  depuis son ouverture. La surveillance, elle, compare au cours du moment : l'écart peut
  suffire à toucher le SL ou le TP dès le premier contrôle. C'est l'explication la plus
  probable, à vérifier (je n'ai pas regardé l'issue des positions). Si elle se confirme,
  c'est un défaut de mesure, pas une stratégie à la seconde : à corriger quel que soit
  l'horizon choisi.
- **Verdict :** à écarter tant qu'il n'y a pas de données intrajournalières, d'exécution
  automatique et de coûts nettement sous le mouvement visé.

### Très court terme (1 semaine à 1 mois) : l'horizon naturel du système
- **Déjà là :** des indicateurs journaliers (RSI, MACD, EMA, ATR), des SL/TP en multiples de
  l'ATR journalier, la lecture du registre à J+5 (J+1 et J+10 descriptifs) et le fantôme Jev à J+5.
- **Données :** 2 ans de barres journalières pour 23 actifs. C'est suffisant.
- **Coûts :** 5 % du mouvement hebdomadaire typique hors crypto, 22 % en crypto. Ils pèsent lourd sur les cryptos.
- **Ce qui manque :**
  - un prix d'entrée actuel (voir ci-dessus) ;
  - une sortie cohérente avec l'horizon : le paper n'a pas de sortie à date, et une position
    reste ouverte jusqu'au SL, au TP ou à un signal inverse (3 positions ont dépassé 30 jours) ;
  - tes frais Revolut réels ;
  - `signal_results` alimentée.
- **Verdict :** réaliste. C'est l'horizon à piloter en premier, à condition de mesurer les frais réels.

### Court terme (3 à 8 mois) : réaliste en coûts, lent à valider
- **Déjà là :** pas de mesure à cet horizon. Les conseils réels à 4 h s'appuient sur les mêmes
  signaux journaliers, conçus pour des jours ou des semaines.
- **Données :** 2 ans de barres 1d et 5 ans de barres 1wk. Les fondamentaux se limitent aux ratios
  du jour pour 5 actions. Le calendrier des résultats existe (`technical_skills/economic_calendar.py`).
- **Coûts :** 1 à 3 % du mouvement typique.
- **Ce qui manque :**
  - une mesure à J+63 et J+126 au registre (il n'en a pas) ;
  - un rythme de décision hebdomadaire : un cycle de 15 minutes n'apporte rien à 6 mois ;
  - des fondamentaux pour toute la watchlist.
- **Validation :** avec 3 groupes, on compte environ 2 observations indépendantes par groupe et
  par an. Une lecture fiable demanderait plusieurs années.
- **Verdict :** utilisable comme horizon de règles et de suivi, pas comme horizon où l'agent démontre une compétence.

### Moyen terme (1 à 3 ans) : accompagnement, pas décision
- **Déjà là :** le plan réel de type `long_terme` et les règles de patience du conseiller
  (`real_advisor_rules.py`).
- **Données :** 5 ans de barres hebdomadaires, soit 1 à 4 fenêtres sans chevauchement par
  actif. Il n'y a ni historique des comptes, ni bilans, ni modèle de valorisation.
- **Verdict :** non mesurable avec ces données. Le rôle réaliste de l'agent est la
  discipline : répartition, rééquilibrage, alertes de rupture de thèse. Les thèses restent
  écrites par toi.

### Long terme (5 à 10 ans) : hors de portée de l'agent
- **Déjà là :** rien qui dépasse 5 ans.
- **Données :** l'historique le plus long (5 ans en hebdomadaire) est plus court qu'un seul horizon.
- **Verdict :** pas réaliste comme horizon de décision. L'agent peut tenir un calendrier de DCA
  et signaler les écarts à la répartition voulue, rien de plus.

## 5. Proposition

1. **Piloté par l'agent (paper, puis peut-être réel) :** le très court terme, après correction du
   prix d'entrée, ajout d'une sortie à l'horizon et mesure des frais réels.
2. **Règles et suivi, sans prétention de signal :** le court terme. Une mesure à J+63/J+126
   peut être pré-enregistrée au registre, en sachant qu'elle prendra des années.
3. **Accompagnement seulement :** le moyen et le long terme (DCA, rééquilibrage, alertes de thèse).
4. **Écarté pour l'instant :** le « galactique ».

## 6. Décisions qui t'attendent

- Quelle correspondance entre tes 5 horizons et les 4 plans de `seed_plans.py` (renommer,
  ajouter un plan, ou garder les libellés actuels) ?
- Le prix d'entrée paper : tranché et codé (registre v1.8, §9.4) : prix frais de moins de 15 min
  à l'ouverture, anti-boucle de 24 h.
- Faut-il ajouter une sortie à date au paper (J+5 comme le registre, ou J+20) ?
- Faut-il pré-enregistrer une mesure à J+63/J+126 pour le court terme ?
