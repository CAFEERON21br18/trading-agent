# TODO — hors périmètre

Points relevés depuis la Phase 4 (audit du chat stratégique, 01/10/2026). Chacun fera l'objet d'un
travail séparé.

Nettoyage du 23/11/2026 (`docs/NETTOYAGE_JOURNAL.md`) : les entrées faites ou sans objet sont sorties ;
leur liste est en fin de fichier, avec ce qui les a closes. Les numéros des entrées restantes n'ont
pas changé : les renvois « TODO §N » du code et des autres documents restent lisibles. Les entrées
citent des fonctions plutôt que des numéros de ligne.

## Lot comportement — après la lecture Q3.a

Cinq corrections connues, volontairement non faites : chacune change des décisions de l'agent (veto,
taille de position, ou statistiques lues par une décision). Aucune ne se code avant la lecture Q3.a,
et **chacune exige d'abord un critère commité dans `docs/REGISTRE_CRITERES.md`** : ce qui sera
mesuré, sur quel horizon, avec quel seuil, et la date d'effet.

1. **Arrêt d'urgence fondé sur la valeur réelle du portefeuille paper.** Les contrôles
   (`verifier_capital_minimum` du Risk Manager, `lancer_routine_quotidienne`,
   `config.afficher_config`) comparent `config.CAPITAL`, constante lue du `.env`, à
   `CAPITAL_STOP_THRESHOLD` (700 €). Le P&L n'entre jamais dans `CAPITAL` : l'arrêt ne peut pas se
   déclencher. Voir `docs/AVANT_ARGENT_REEL.md`, condition 7.
2. **Veto Fear & Greed appliqué aussi au tactical** (détail au §21). Le tactical appelle
   `analyser_actif_complet` sans `sentiment_global` : l'override Fear & Greed ne s'y active jamais.
3. **Risque réduit réellement appliqué en mode défensif.** `risque_par_trade_pct()`
   (`agents/paper_trader/portfolio.py`) n'est lu que pour l'affichage ; le dimensionnement utilise
   `config.RISK_PER_TRADE_PCT` (`valider_signal`, Risk Manager).
4. **Correction de `setups_similaires`** (détail au §25) : la décision BUY ou SELL est comparée à
   une colonne qui contient LONG ou SHORT, la requête ne trouve jamais rien.
5. **Alimentation de `signal_results`** (détail dans l'entrée PRIORITÉ HAUTE ci-dessous) : la table
   n'est écrite par aucun cycle ; le winrate par actif, l'intuition, l'override « track record » et
   l'allocation du Budget Manager en dépendent.

Autres points dont la correction changerait des décisions, décrits plus bas : §12, §14, §20, §22,
§26, §27, §29 ; et le rôle des leçons (`memory/lessons_learned.md` ne donne à l'intuition qu'une
phrase de « raisons », sans effet sur la décision).

Décision déjà inscrite au registre et non appliquée : `EXCLURE_BOUCLES_STATS` devait passer à 1 après
le 28/10/2026 (registre v1.8 et v1.9, §9.5). Au 23/11/2026 la variable est absente du `.env` de la
tour, donc à 0 : les modes du Budget Manager, la porte paper défensive, le suivi d'intuition et les
écritures de leçons et de patterns comptent encore les positions « boucle ».

## ⚠️ PRIORITÉ HAUTE — `signal_results` jamais alimentée en production (données de démo purgées le 08/10/2026)

- Seul écrivain : `cloturer_signal()` (`agents/trade_journalist/journalist.py`),
  appelé uniquement par la démo du Trade Journalist
  (`agents/trade_journalist/demo_performance.py`, valeurs fictives
  BTC/ETH/AAPL ; isolée depuis le 08/10, voir plus bas). Les signaux de la
  routine quotidienne (`agents/orchestrator.py`, `enregistrer_signal`) ne sont
  jamais clôturés. Relevé le 07/10/2026 (carte du code, Phase 3). **Reste
  ouvert** : après la purge, la table est vide et aucun code de production ne
  l'alimente.
- Lecture statique : **des décisions lisent des statistiques issues de cette
  table** (jointure `INNER JOIN signal_results`) :
  - `utils/memory_lookups.py` (`winrate_par_actif`, `winrate_recent`,
    `pertes_consecutives_recentes`, `setups_similaires`) → contexte du pipeline
    groupé (`agents/skills/_memory_context.py` → `pipeline_grouped.py`), donc
    coefficient de taille des BUY/SELL ;
  - `performance_tracker.stats_par_actif` / `calculer_stats_globales` →
    `mettre_a_jour_performance_md()` (routine quotidienne) →
    `memory/performance_tracker.md` → `memory_reader.lire_winrate_par_actif` →
    override « track record défavorable » (`_verifier_overrides`,
    `agents/decision_regles.py`), intuition (`agents/intuition.py`), et
    `winrate_historique` du Budget Manager (`_decision_to_demande`,
    `agents/paper_trader/cycle.py`, allocation) ;
  - `verifier_alerte_degradation` (email « dégradation perf ») et le contexte
    du chat (`calculer_stats_globales`).
- **Constat du 08/10/2026 (lecture seule)** : la table ne contenait que 3
  lignes, toutes issues du bloc `__main__` de démonstration de
  `performance_tracker.py`, lancé sur la vraie base le 15/04/2026 à 17:07:46
  UTC : SIG-0001 BTC-USD +10.11 %, SIG-0002 ETH-USD −4.69 %, SIG-0003 AAPL
  +5.57 %. SIG-0004 (SOL-USD) et SIG-0005 (SPY), du même bloc, sans clôture.
  D'où `calculer_stats_globales` : winrate 66.7 %, profit factor 3.35 ; et
  dans `memory/performance_tracker.md` : BTC-USD et AAPL 100 %, ETH-USD 0 %,
  sur 1 trade chacun (fichier ainsi depuis son premier commit, ecc6e7e,
  04/05/2026).
- **Effet mesuré** (registre du 06/10 18:30 UTC au 08/10 13:16 UTC, 2 253
  décisions) :
  - jamais déclenchés, faute de trades (1 par ticker) : override « track
    record » (≥ 5 trades), `_seuil_confiance_requis` (≥ 3), intuition (≥ 3).
    0 décision et 0 confiance modifiées par l'intuition (reconstitution à
    partir du score, des overrides et des confiances enregistrés) ;
  - Budget Manager, sans minimum de trades (§26) : `winrate_actif` 100 sur
    BTC-USD (35 lignes) et AAPL (13), 0 sur ETH-USD (2), 50 par défaut
    ailleurs. 3 décisions soumises (AAPL le 07/10, ETH-USD les 07/10 et
    08/10), toutes refusées, et elles l'auraient été avec 50 : 0 allocation
    changée ;
  - pipeline : prior bayésien de 0,67 pour tous les tickers (« Fallback
    global : 67 % winrate sur 3 derniers trades ») ; effet sur les verdicts
    non mesurable (ancien §24, note portée par
    `docs/REGISTRE_CRITERES.md`) ; les taux de base, eux, ne trouvent jamais de setup
    (§25) ;
  - affichage seulement : chat (12 prompts dans `message_audit`), 44 rapports
    quotidiens du 25/08 au 08/10 (« 🧠 Mémoire : winrate 100% sur 1
    trade(s) »).
- **Données de démo purgées le 08/10/2026** :
  - démo isolée (base et fichiers mémoire temporaires) et `generer_signal_id`
    par plus grand numéro + 1 au lieu de `COUNT(*) + 1`, qui aurait redonné
    un numéro existant après la purge (commit ea842f6) ;
  - `scripts/purger_signaux_demo.py --appliquer` (commit 769e4dd), lancé par
    l'utilisateur : SIG-0001 à SIG-0005 supprimés de `signal_results` (3
    lignes) et de `signals` (5 lignes), sauvegarde préalable
    `data/sauvegardes/database_avant_purge_demo_20261008.db`,
    `memory/performance_tracker.md` régénéré ;
  - `memory/trade_journal.md` garde les 5 entrées du 15/04 (affichage du
    dashboard seulement, aucune décision ne le lit).

## 2. Classement des erreurs LLM par sous-chaîne : reste Groq

Gemini est corrigé depuis Q5 (06/10/2026) : classement d'après le quotaId (`utils/gemini_erreurs.py`).

- Groq (`utils/llm.py::_try_groq`) : `"429" in err or "rate" in err` → `rate_limit_groq`, avec une
  nouvelle tentative dans 60 s.
- Le 01/10 (`message_audit`, enregistrement n° 2), le 429 venait du **quota quotidien de jetons**
  (TPD : 200 000 par jour), pas d'une limite par minute : le délai de 60 s est faux dans ce cas.
- À confirmer côté Gemini, avec les messages bruts journalisés depuis Q5 : l'heure de la remise à
  zéro quotidienne (les retryDelay longs pointent vers 01h00, heure de Lisbonne, mais certains 429
  « par jour » n'annoncent que quelques secondes).

## 3. Bandeau d'erreur générique du chat

- `agents/chat/_llm.py`, `MESSAGES_ERREUR_UI["both_failed"]` affiche
  « Gemini en quota et fallback Groq KO » quelle que soit la cause réelle
  (clé invalide, 503, réseau, quota Groq…).
- Les erreurs réelles des deux fournisseurs sont désormais enregistrées dans
  `message_audit.chaine_de_fallback`, mais pas montrées à l'utilisateur.

## 4. Conseils réels non répondus chargés en entier à chaque message

- `agents/chat/context_builder.py::build_context` charge
  `lire_conseils_actifs()` à chaque message du chat : 1 248 conseils non
  répondus au 01/10/2026, soit environ 504 000 caractères.
- Seul leur nombre est utilisé (`agents/chat/_formatters.py`,
  `len(advice)`). La liste n'est jamais injectée dans le prompt.
- Depuis la Phase 4, `message_audit` n'en stocke qu'un extrait (20 conseils
  et le total), mais le chargement complet a toujours lieu.

## 5. `memory/metacognition_log.md` : ne jamais l'utiliser comme source

Règle reprise dans `CLAUDE.md` (section Mémoire) le 23/11/2026. Le détail reste ici.

- **Aucun code ne le lit** : seul `agents/skills/_log.py` y écrit. Ni le
  pipeline (ses signaux comportementaux viennent de la base), ni
  `memory_reader`, ni le module `learner`, ni la page Memory du dashboard.
- **Ne jamais l'utiliser comme source du registre de signaux** : texte libre,
  aucune origine enregistrée (cycle, chat, conseiller réel), et la période
  22/06 → 02/09/2026 n'est pas vérifiable (messages du chat effacés, aucun
  journal sur ce PC).
- Entrées venant du chat, connues (rapport E3 du 03/10/2026) :
  ligne 18778 (01/10 22:07 UTC, AMAT, **confirmée** par `message_audit`),
  ligne 3982 (02/09 00:19 UTC, AAPL, **probable**). Non marquées
  volontairement : une modification sur place entrerait en concurrence avec
  les cycles qui écrivent dans le fichier. Depuis E2, le chat n'y écrit plus.

## 7. `PUT /api/plans/<id>` n'est pas plafonné

`POST /api/plans` applique depuis le 16/10/2026 le plafond du mode plan du chat, et toutes les routes
modifiantes du dashboard exigent l'en-tête `X-AlphaSignal: 1` (`dashboard/api/garde_ecriture.py`).

- Reste : `PUT /api/plans/<id>` (`dashboard/api/plans_routes.py`, `plans_validation.py`) ne contrôle
  que les types et les bornes (montants ≥ 0, pourcentage du budget entre 0 et 100, statut dans
  `STATUTS`). Pour plafonner une modification, il faudrait retirer la réservation actuelle du plan,
  calcul interne à `agents/chat/_plan_budget.py`, gelé pendant le suivi de la consigne v2 (§33).
- `POST /api/plans` hérite du mélange € et $ du §33.

## 8. JUSTESSE — P&L inconnu présenté comme 0 : ce qui reste

Corrigé le 06/10/2026 pour le chat (`agents/chat/_pnl_latent.py`) et pour la page Overview
(`dashboard/api/queries.py`) : positions valorisées au dernier prix relevé par les cycles
(`data/cache/dernier_prix/`), couverture et heure affichées, sinon « non disponible ». Restent :

- **P&L réalisé réel** : `resume_portefeuille` (`utils/real_portfolio_db.py`) compte 0 pour une
  position réelle close sans `realized_pnl` (aucune au 06/10).
- **Mode défensif** : `est_en_mode_defensif` (`agents/paper_trader/portfolio.py`) compte un P&L
  inconnu comme « pas une perte » (aucune position close sans P&L au 06/10). La fonction sert à la
  porte du Paper Trader : la corriger demande un critère.
- **Défaut inverse** (`agents/chat/_extraction.py`) : une performance sur 1 mois de 0,0 % devient
  `None` (test `if change_1m`), un RSI sans aucune baisse devient `None` au lieu de 100.

## 12. R:R structurellement constant à 2.0

- `calculer_targets` (`agents/analysts/risk_manager/position_sizer.py`)
  place l'objectif 1 à 2 × la distance du stop : le R:R de l'objectif 1 vaut
  toujours 2.0 (741 signaux sur 741 au 06/10/2026, avant comme après P10).
- Le filtre du Risk Manager (`R:R < RR_MINIMUM` = 1.2,
  `agents/analysts/risk_manager/manager.py`) ne peut donc rejeter
  que des données manquantes (depuis P9 : « Données de prix manquantes ») ;
  il ne filtre aucun trade sur sa qualité.
- Décision de conception à prendre plus tard (par exemple un objectif fondé
  sur les niveaux de marché, ou la suppression de ce filtre).

## 14. Découvertes des explorateurs jamais analysées faute de prix

- Le tactical analyse à chaque passage les 5 premières entrées de la queue
  (`scripts/cycle_tactical.py`, étape 3). Les indicateurs ne lisent que la
  table `prices`, qui ne contient que les 23 actifs de la watchlist (seule
  la watchlist est collectée par `scripts/fetch_data.py`), et les
  explorateurs excluent la watchlist de leur scan (`agents/explorers/base.py`) :
  **aucun ticker de la queue n'a donc de prix** (sauf un actif retiré de la
  watchlist, dont les anciennes barres resteraient en base). Résultat :
  « Aucune donnée en BDD pour X [1d] », les 4 sous-agents NEUTRE,
  confiance 0, décision HOLD avec un score de 0.
- Mesures (lecture seule, 06/10/2026) :
  - 40 tickers distincts sans données dans le log du tactical les 05 et
    06/10 (USDMXN=X à lui seul : 330 messages) ;
  - aucune position paper ouverte sur un actif hors watchlist, depuis le
    début (16 tickers, tous dans la watchlist) ;
  - l'étape de la queue dure 3,0 s par passage en médiane (p90 5 s,
    74 passages) ;
  - les explorateurs téléchargent déjà 6 mois de barres journalières par
    actif scanné (`screening_helpers.df_avec_indicateurs`, cache 5 min),
    puis les jettent.
- Dans le registre, ces décisions sont marquées `suite.resultat =
  "sans_donnees"` (R2c) et exclues des analyses (REGISTRE_CRITERES v1.1).
- **Décision à prendre plus tard, deux options :**
  - **(a) Collecter les prix des actifs de la queue avant l'analyse.**
    - Coût : pour chaque nouveau ticker, les trois téléchargements de
      `fetch_data` (2 ans en 1d, 5 ans en 1wk, 60 jours en 1h), soit environ
      1 200 lignes de `prices` par action et 2 400 par crypto, et quelques
      secondes par ticker
      (environ 40 nouveaux tickers en deux jours) ; ensuite un
      rafraîchissement de 10 jours à chaque passage, ou des barres figées
      comme avant P10. Plus d'appels à Yahoo, déjà en 429 sur les flux RSS.
      Variante moins chère : enregistrer les 6 mois déjà téléchargés par
      l'explorateur, mais l'historique est alors plus court que pour la
      watchlist.
    - Effet : les découvertes reçoivent une vraie analyse et peuvent ouvrir
      des positions paper hors watchlist. L'univers traité s'élargit au-delà
      des groupes de REGISTRE_CRITERES (ces actifs y sont « comptés seuls ») ;
      l'analyse fondamentale de ces actifs reste limitée par les quotas
      d'Alpha Vantage.
  - **(b) Ne plus analyser la queue.**
    - Coût : quelques lignes (supprimer ou désactiver l'étape 3) et la doc
      (CLAUDE.md) à aligner.
    - Effet : environ 3 s gagnées par passage, 5 recherches de news en moins
      par passage (NewsAPI est déjà saturé : 742 réponses 429 dans le log du
      tactical le 06/10), environ 450 lignes vides en moins par jour dans le
      registre. Aucun effet sur les trades : faute de prix, la queue ne peut
      ouvrir aucune position aujourd'hui. Les explorateurs ne servent plus qu'aux alertes email
      (score ≥ 7) ; leurs découvertes ne sont jamais évaluées.

## 17. Fonctionnalités annoncées mais jamais appelées : brancher ou supprimer ?

Relevé le 07/10/2026 avec Graphify (modules sans aucune arête entrante),
confirmé par grep et par `git log -S` sur tout l'historique : **aucun de ces
modules n'a jamais été importé** depuis son ajout. Ce n'est pas une régression,
ils n'ont jamais été branchés. Ne rien supprimer avant décision.

- ~~**`agents/knowledge/pretrade_analysis.py`**~~ **branché le 17/10/2026**, avec
  `chart_reading.py`, dans le rapport quotidien et son email : analyse condensée des
  seuls BUY et SELL du cycle (`agents/rapport_pretrade.py`, via
  `agents/rapport_annexes.py`), affichage seulement, bornée à 60 s. Aucun des deux
  modules n'appelle un LLM. Section 3 : « non disponible ». Constat d'origine :
- **`agents/knowledge/pretrade_analysis.py`** (ajouté le 19/06/2026, a404ac6, v5.0)
  - Censé faire : l'« analyse pré-trade en 8 sections » de CLAUDE.md (modules
    v5.0), en mode complet (cycles quotidien et stratégique, décisions
    importantes) ou condensé (tactical, couches 1, 7 et 8), avec rendu Markdown.
  - Entraîne `agents/knowledge/chart_reading.py` (« lecture multi-timeframe en
    5 couches », lui aussi listé dans CLAUDE.md) : son seul importeur est
    `pretrade_analysis.py`, donc il n'est jamais exécuté non plus.
  - La section 3 (catalyseurs) est un placeholder : « Earnings/guidance non
    implémentés ».
  - Question : brancher (où ? dans le rapport quotidien, l'email d'ouverture
    de position ou le chat) ou supprimer les deux modules et retirer leur
    mention de CLAUDE.md ?
- **`agents/paper_trader/rotation.py`** : **branché en mode fantôme le 17/10/2026**
  (`agents/rotation_fantome.py`, fin du cycle quotidien). Slots pleins et opportunité
  refusée (registre du jour, lu en mode=ro) : la position qu'elle aurait fermée va dans
  la table `rotation_hypothetique` de `database.db` ; rien n'est fermé. `ROTATION_ACTIVE`
  vaut 0 ; à 1, le code refuse d'agir. L'activer resterait un changement de décision :
  critère du registre d'abord. Constat d'origine :
- **`agents/paper_trader/rotation.py`** (ajouté le 19/06/2026, a404ac6, v5.0)
  - Censé faire : la « rotation v5 » du Paper Trader (CLAUDE.md). Si les
    `MAX_POSITIONS_SIMULTANEES` slots sont pleins et qu'une opportunité arrive
    avec au moins 2 points de confiance de plus que la position la plus faible
    (ou un score composite supérieur de plus de 1.5), proposer de fermer
    cette position.
  - Aujourd'hui, quand les slots sont pleins, la nouvelle opportunité est
    simplement refusée.
  - Question : brancher (changerait des décisions : fermetures anticipées,
    à évaluer avec REGISTRE_CRITERES, et à enregistrer dans le registre) ou
    supprimer et retirer « rotation v5 » de CLAUDE.md ?
- ~~**`agents/report_sections.py`**~~ **branché le 17/10/2026** dans le rapport
  quotidien et son email (via `agents/rapport_annexes.py`), réécrit pour les
  décisions actuelles (BUY/SELL, `{ticker, decision, analyses}`) : News par NewsAPI
  seulement, 1 requête par actif BUY ou SELL et 10 au plus par jour (compteur
  `data/rapport_newsapi.json`), « non disponible » sans clé, au plafond ou en erreur ;
  Fondamentaux tirés de l'analyse du cycle, sans nouvel appel Alpha Vantage.
  Affichage seulement. Constat d'origine :
- **`agents/report_sections.py`** (présent dès le commit initial v4.1 du
  04/05/2026, ecc6e7e)
  - Censé faire : deux sections du rapport quotidien pour les signaux
    ACHAT/VENTE, News (3 articles NewsAPI par actif) et Fondamentaux. Sa
    docstring dit « appelée depuis orchestrator.py », ce qui n'a jamais été le
    cas dans l'historique git.
  - Le rapport actuel (`agents/orchestrator.py`) n'a pas ces sections. Le
    module filtre sur le vocabulaire v4 (`signal` = « ACHAT »/« VENTE ») : à
    vérifier contre le format actuel des décisions (BUY/SELL) avant tout
    branchement.
  - Question : brancher (coût NewsAPI : 1 requête par signal actif) ou
    supprimer ?

## 20. L'intuition force BUY après un veto, y compris sur un signal baissier

- `consulter_intuition` (`agents/intuition.py`, bloc « Override possible ») : si la décision provisoire est `NO_TRADE`
  (donc après **n'importe quel** override de `_verifier_overrides` :
  veto du Risk Manager, Fear & Greed extrême) et que `ajustement ≥ 2`,
  l'intuition renvoie `override_decision = "BUY"`. `decider()` l'applique
  (étape 4 de `decider`, `agents/decision_engine.py`) en style `learning` (×0.2, seuil de
  confiance 4). Le veto est levé **et la direction peut être inversée** :
  un signal technique VENTE bloqué devient un achat. Relevé le 08/10/2026.
- En pratique, `ajustement ≥ 2` demande un winrate ≥ 70 % sur ≥ 3 trades et
  au moins un pattern trouvé dans `market_patterns.md` (le pilier
  géopolitique, jamais alimenté, a été retiré le 23/11/2026). Le veto « track record » ne peut pas être levé
  (winrate < 35 % donne déjà -2). Le veto Risk Manager est re-validé par le
  Paper Trader (`executer_ouvertures`, `agents/paper_trader/cycle.py`), mais en LONG avec le
  budget alloué, donc sur une autre question que celle rejetée.
- Note : la docstring de `consulter_intuition` décrivait `ajustement` comme « à ajouter
  au score composite ». Corrigée le 23/11/2026 : `decider()` ne l'ajoute jamais au
  score, il ne sert qu'au seuil d'override et au pressentiment.
- **Critère à pré-enregistrer avant correction** (REGISTRE_CRITERES) : ce
  qui serait mesuré (rendement des BUY issus d'un override intuitif après
  `NO_TRADE`, comparés à leur absence), sur quel horizon, avec quel seuil.
  Ne rien corriger avant.

## 21. Veto Extreme Greed contournable (quotidien) et inactif (tactical)

- Cycle quotidien : `_verifier_overrides` (`agents/decision_regles.py`)
  bloque un achat si F&G ≥ 80. L'intuition (§20) peut lever ce `NO_TRADE` en
  BUY, et **rien ne revérifie le F&G en aval** (le Paper Trader ne re-valide
  que le risque) : on peut acheter exactement dans le cas que le veto devait
  empêcher.
- Tactical : `scripts/cycle_tactical.py` appelle
  `analyser_actif_complet(t)` sans `sentiment_global`, donc `context` n'a pas
  de `fg_valeur` : l'override F&G (Extreme Fear comme Extreme Greed) **ne
  s'active jamais** dans le tactical, ni dans `reevaluer_position`. Les deux
  cycles appliquent donc des règles différentes au même actif. Relevé le
  08/10/2026.
- **Critère à pré-enregistrer avant correction** : transmettre le F&G au
  tactical ou fermer le contournement change des décisions ; décider d'abord
  ce qui serait mesuré, sur quel horizon, avec quel seuil.

## 22. Le tactical n'évalue que les 8 premiers actifs sans position

- `scripts/cycle_tactical.py` : `[:8]` sur la watchlist hors
  positions ouvertes. Dans l'ordre actuel du fichier, ce sont presque
  toujours BTC, ETH, SOL, HBAR, CRO, AAPL, TSLA, NVDA. `INDICES_US` (SPY, QQQ,
  VOO, NQ=F, rangs 18 à 22 sur 23) n'est atteint que si au moins 10 actifs
  placés avant ont une position ouverte ; `SEMIS_IA` se réduit à NVDA.
  La sélection dépend de l'ordre du fichier (ancien §16). Relevé le
  08/10/2026.
- Conséquence : les groupes de REGISTRE_CRITERES §0.1 sont très déséquilibrés
  dans les décisions du tactical, ce qui biaise la lecture Q3.a (couples
  examinés par le pipeline, majoritairement issus du tactical).
- **Critère à pré-enregistrer avant correction** : changer la sélection
  (rotation, tirage, tous les actifs) change les décisions et la composition
  des données Q3 ; fixer d'abord la règle et sa date d'effet dans
  REGISTRE_CRITERES.

## 25. Taux de base du pipeline : `setups_similaires` ne trouve jamais de setup

- `executer_pipeline` (`agents/skills/pipeline_grouped.py`) passe la décision (`BUY` ou
  `SELL`) comme direction à `contexte_base_rates`, puis à `setups_similaires`
  (`utils/memory_lookups.py`), qui la compare à `s.direction`. Or les
  signaux sont enregistrés en `LONG` ou `SHORT` (`agents/orchestrator.py` ; 613
  LONG et 153 SHORT au 08/10). La requête ne renvoie jamais rien : le LLM
  reçoit toujours « Aucun historique de trades BUY sur la classe … ».
- Sans effet tant que `signal_results` est vide, mais le verdict « base
  rates » (×0,7 sur la taille) restera aveugle une fois la table alimentée.
  Relevé le 08/10/2026 (purge des signaux de démo), non corrigé.

## 26. Budget Manager : winrate par actif utilisé sans minimum de trades

- `_decision_to_demande` (`agents/paper_trader/cycle.py`) transmet `perf["winrate_pct"]` (lu dans
  `memory/performance_tracker.md`) sans condition sur le nombre de trades, et
  `_calculer_score` (`agents/budget_manager/arbitrator.py`) en fait le score d'allocation :
  confiance × (1 + winrate/100) × urgence. **Un seul trade suffit** à doubler
  ce facteur (100 % : ×2,0) ou à le réduire (0 % : ×1,0), contre ×1,5 par
  défaut (50 %).
- Les autres lecteurs du même winrate exigent 3 trades (intuition) ou 5 (override « track record »). Relevé le
  08/10/2026 (purge des signaux de démo), non corrigé.
- Repris de l'ancienne entrée de tête (décisions du tactical, close) : quand le capital
  investissable est épuisé, le Budget Manager rend les demandes sans `raison_refus`
  (`traiter_demandes`). La ligne du registre porte alors la raison générique « BM en attente »
  (`executer_ouvertures`, `agents/paper_trader/cycle.py`), pas le message « Capital investissable
  épuisé ». Le corriger change le texte d'une ligne du registre.

## 27. Actifs sans fondamental ; quota Alpha Vantage épuisé par le tactical

Constat du 08/10/2026. **Correction = changement de décision : critère pré-enregistré d'abord**
(`docs/REGISTRE_CRITERES.md`). Fait depuis : cache de 10 min des données CoinGecko
(`agents/analysts/fundamental_analyst/onchain.py`, registre v1.9 §9.8 b). Restent :

- **Actifs sans fondamental** (registre, cycles quotidiens des 07 et 08/10 : confiance fondamentale
  nulle pour 11 actifs sur 23) :
  - AMAT, AMD, CEG, LITE, MU, VRT, VST et CL=F : absents de `ACTIONS_US` et de `ETF_INDICES`
    (`agents/analysts/fundamental_analyst/analyst.py`) : ni fondamental, ni requête ;
  - HBAR-USD et CRO-USD : absents de `TICKER_TO_COINGECKO` (`onchain.py`) ;
  - SOL-USD : présent dans cette table ; cause non vérifiée.
- **Aucun cache Alpha Vantage** (25 requêtes par jour). Le tactical appelle OVERVIEW pour les 5
  actions de `ACTIONS_US` à chaque passage : 405 à 468 refus par jour du 25/09 au 08/10 dans
  `logs/task_tactical.log`. Le cycle de 07h30 n'a reçu aucune donnée Alpha Vantage du 24/09 au
  08/10 : le fondamental de ces 5 actions reposait sur la seule position du prix dans sa fourchette
  de 52 semaines (`position_52_semaines`, `macro.py`), sans P/E, EPS ni earnings.
- Banc de rejeu du chat : c'est `scripts/_chat_a_blanc.py` (`_alpha_vantage_coupe`) qui coupe Alpha
  Vantage ; le prompt d'un cas manuel a donc presque toujours la même lacune que le chat réel.

## 29. Paper trader et fantôme Jev : 1 € = 1 $ sur les actifs cotés en dollars

Relevé le 13/10/2026 (audit D1, lecture seule). **Ne pas corriger avant la fin
des fenêtres de mesure du registre (`docs/REGISTRE_CRITERES.md`) et de son §7
(observation Jev)** : une correction serait une rupture de série.

- `calculer_taille_position` (`agents/analysts/risk_manager/position_sizer.py`) divise des euros par
  un prix yfinance en dollars : `taille_par_risque = risque_max_eur /
  distance_stop` et `taille_par_budget = budget_par_pos / prix_entree`. Ensuite,
  `montant_investi = taille_unites × prix_entree` est un montant en dollars,
  affiché « € ».
- Même calcul dans le fantôme Jev : `agents/jev/fantome_regles.py`
  (`quantite = montant / prix`).
- De fait, le capital, les montants investis, le P&L paper et le P&L du fantôme
  sont en USD libellés « € » sur les actifs cotés en dollars (actions US,
  cryptos `-USD`, contrats `=F`). Les rendements du registre sont des rapports
  de prix : l'unité ne les change pas. Note de fait dans le registre, v1.6 (§4).

## 31. `plan_advisor` : `sous_repartition` et `max_position_size` non contrôlés

`rules["repartition"]` du plan global est contrôlée depuis le 17/10/2026
(`agents/plan_repartition.py`). Restent :

- **`sous_repartition` n'est pas contrôlée** : ses catégories ne désignent ni un sous-plan ni, sans
  ambiguïté, une liste d'actifs. Dans un sous-plan, deux catégories ne correspondent à une liste
  d'actifs que par la ressemblance du nom ; dans un autre, rien ne permet de classer une action
  entre deux catégories. Il faudrait une liste d'actifs par catégorie, sous le même nom ;
- `max_position_size` reste vide dans les 4 plans : `verifier_taille_position` ne peut toujours
  rien signaler.

## 32. `utils/real_portfolio_db.py` : 707 lignes (règle 5)

Relevé le 13/10/2026. Le fichier mélange schéma et migrations, budget, positions, conseils, plans,
progression et alertes. Tout le portefeuille réel passe par lui : son découpage aura sa propre
session (il n'a pas été découpé au nettoyage du 23/11/2026).

- En attendant, n'y ajouter aucune ligne nette : le nouveau code va dans de nouveaux modules.
- À faire au découpage : `get_real_budget_summary` et `progression_plan` n'ont plus d'appelant en
  production depuis le 14/10/2026 (ancien §35), mais quatre modules de test s'en servent comme
  calcul de référence (`test_real_conversion`, `test_real_sans_prix`, `test_real_devise`,
  `test_plan_sans_position`) : réécrire ces tests avant de supprimer les deux fonctions.
- `CREATE TABLE market_regime` est dans ce fichier, alors que la table est lue et écrite par
  `agents/technical_skills/market_regime.py` : à ranger au découpage.
- La colonne `devise` de `real_investments` n'est créée par aucun code du dépôt (§43) : à mettre
  dans le schéma au découpage.
- Autres fichiers de code encore au-dessus de 200 lignes après le nettoyage du 23/11/2026 :
  `dashboard/templates/real.html` (550) et `plans.html` (255), dont le JavaScript en ligne n'a pas
  été sorti (un test interdit les `fetch` modifiants hors des gabarits qui étendent `base.html`,
  et quatre autres lisent le script dans le gabarit) ; `agents/orchestrator.py` (224), dont les deux
  grandes fonctions ne peuvent pas bouger sans toucher aux tests qui remplacent des noms sur ce
  module. Détail : `docs/NETTOYAGE_JOURNAL.md`, lot 8.

## 33. D1, partie chat : reportée après le suivi de la consigne v2

Relevé le 13/10/2026 ; report décidé le 14/10/2026. Les montants des 8 positions
réelles sont en dollars (constat du 08/10) ; le capital total réel est en euros
(confirmé le 14/10). La partie hors chat est corrigée par les commits D1 du
14/10. Pendant la fenêtre de suivi de la consigne v2 (jusqu'au 27/10, peut-être
jusqu'au 10/11), il est interdit de toucher au prompt du chat et au contrôle des
chiffres. Restent donc à faire après la fenêtre :

- la section « PORTEFEUILLE RÉEL » du prompt : `agents/chat/_llm.py:43-44`
  (investi et P&L réalisé libellés « € ») et `:62` (prix d'entrée libellé
  « € ») ;
- `agents/chat/_plan_budget.py:46-90` : le plafond d'un nouveau plan soustrait
  du capital (€) l'investi ($), et le budget restant soustrait de l'€ et du $.
  Affichage et refus sont libellés « € ». Au 13/10, le mélange ne change pas le
  refus : le Plan Global à 100 % réserve tout le capital, et le plafond est ≤ 0
  avec ou sans conversion ;
- `agents/chat/_formatters.py:46-53` : total investi et P&L réalisé libellés
  « € », prix d'entrée sans unité ;
- `agents/chat/_verif_chiffres.py` : ajouter `$` et `USD` aux unités reconnues,
  avec une nouvelle `VERSION`.

## 42. Hygiène des explorateurs : ce qui reste

Faits le 19/10/2026, sans effet sur les décisions : univers crypto nettoyé
(`agents/explorers/crypto_explorer/universe.py`, `est_exclu`) et une entrée par ticker et par jour
dans la queue (`agents/explorers/queue_manager.py`). Le critère des explorateurs est resté à l'état
de brouillon (fichier retiré du dépôt le 23/11/2026, gardé par l'histoire git). Restent ouverts :

- EMA 200 vide : les explorateurs chargent 6 mois de barres (`df_avec_indicateurs`,
  `agents/explorers/screening_helpers.py`), trop peu pour une moyenne à 200 jours ;
- le biais d'ordre des explorateurs face à une queue pleine ;
- le prix des tickers de la queue (§14).

## 43. Reliquats du nettoyage du 23/11/2026

Points laissés par les entrées sorties, ou relevés pendant le nettoyage. Aucun ne change une
décision, sauf mention.

- **Audit métacognitif** (`audit_metacognitif`, `agents/decision_engine_meta.py` ;
  `METACOG_AUDIT_ENABLED`, éteint par défaut ; ancien §6). Son résultat n'est lu par aucun code, mais
  l'interrupteur entre dans l'empreinte des paramètres du registre (`parametres_actifs`,
  `utils/registre.py`) : le retirer change l'empreinte de chaque passage. À faire avec une note de
  rupture d'empreinte au registre, hors fenêtre de lecture.
- **Entrée CONVICTION de `PARAMETRES`** (`agents/budget_manager/strategy.py`) : plus atteinte par
  aucun code, gardée pour la même raison (`MODES_BM` de l'empreinte). À retirer avec la même note.
- **Trailing stop sans commande** : `activer_trailing_stop` et `desactiver_trailing_stop`
  (`agents/technical_skills/trailing_stop.py`) n'ont plus d'appelant depuis le retrait de la route
  `POST /api/positions/<id>/trailing-stop`. Le moniteur suit toujours le stop des positions où
  `trailing_stop_active` vaut 1. À décider : retirer tout le trailing stop (changement de
  comportement si une position l'a actif), ou lui redonner une commande.
- **`scripts/jev_essai.py`** (essai d'un appel réel à TypeSafe, sans écriture en base) : absent de
  l'inventaire, il n'existait alors que sur le dépôt distant. Ni classé, ni lancé, ni branché.
  L'ancien §23 donnait son usage : `python scripts/jev_essai.py BTC-USD`, code de sortie 0 avec
  « Modèle renvoyé : jev-1.13.0 », 1 pour un autre modèle, 2 sans clé, 3 si l'appel échoue.
- **`scripts/show_access_urls.py`** affiche des adresses `http://<ip>:8080` qui ne répondent plus
  (le dashboard n'écoute que sur 127.0.0.1) et un lien de téléchargement pour Mac : à réécrire ou à
  supprimer (`scripts/setup_tailscale.py` affiche déjà la bonne adresse).
- **Colonne `devise` sur une base neuve** : `initialiser_real_db` ne la crée pas ; le script de
  migration D1, appliqué sur la tour, a été retiré du dépôt (voir §32).
- **`logs/task_*.log` jamais bornés** (ancien §1) : `scripts/install_tasks_windows.ps1` redirige la
  sortie de chaque tâche en ajout (`>>`), sans rotation.
- **Anciens fichiers de `logs/`**, écrits avant le 19/10/2026 : ils peuvent contenir les clés
  NewsAPI et Alpha Vantage en clair ; à supprimer à la main (ancien §37).
- **`scripts/check_status.py`** (ancien §37) : ses contrôles d'API mettent les clés dans l'URL et
  affichent l'exception par `print`, hors du masquage de `utils/logger.py`.
- **`data/lockin_assets.json`** : état du LOCK-IN retiré, plus lu ni écrit ; à supprimer de la tour
  à la main.
- **`graphify-out/graph.json`** de la tour cite les modules supprimés jusqu'à sa prochaine
  régénération (dimanche 20h, ou `scripts\regenerer_graphe.py`).
- **Identifiants de commit** cités dans ce fichier et dans `docs/` : ce sont ceux de l'historique
  d'avant la réécriture du dépôt public (23/10/2026). Les sujets des commits n'ont pas changé :
  `git log --grep` les retrouve.
- Noms inutilisés relevés au passage, non retirés : `SERIES_FRED`
  (`agents/analysts/fundamental_analyst/macro.py`), `REQUEST_TIMEOUT_SEC` (`utils/gemini.py`),
  `logger` de `agents/knowledge/pretrade_analysis.py`.

## 44. Dashboard professionnel (grand livre, mesures, importeurs, pages) : points ouverts

Socle intégré le 24/11/2026 (`ledger/`, `mesures/`, `importeurs/`, `docs/SOCLE_JOURNAL.md`). Pages
« Vue d'ensemble » (`/pro`) et « Mes trades » (`/pro/trades`) ajoutées le 24/11/2026
(`dashboard/pro/`, `docs/PAGES_JOURNAL.md`) : seul ce paquet lit le grand livre. Aucun point
ci-dessous ne change une décision de l'agent.

Points ouverts du README de la source, toujours vrais :

1. **Colonnes du relevé Revolut** : `COLONNES` (`importeurs/revolut_lecture.py`) décrit un format
   générique, jamais confronté à un vrai relevé. À ajuster sur les en-têtes du vrai fichier avant
   le premier import ; l'aperçu de la page « Mes trades » montre le résultat sans rien écrire. Le
   relevé réel et le grand livre restent hors git (règle 9).
2. **Frais du relevé** : l'importeur les déduit de l'écart entre `Total Amount` et quantité × prix,
   au-delà de 0,01. À confirmer sur le vrai relevé ; un ordre sans écart s'affiche « frais non
   détectés ».
3. **Taux EURUSD quotidien** : la table `change` n'est remplie que sur une action de Lucia, le
   bouton « Synchroniser » ou `scripts/ledger_taux.py` ; aucune tâche planifiée. Sans taux dans les
   7 jours qui précèdent une clôture, la page affiche « taux indisponible ».
4. **Dépôts et retraits** : ils sont maintenant enregistrés (table `mouvements`) et la page
   affiche les apports nets. Mais `mesures/courbe.py` attend toujours une série de valeurs où ils
   sont neutralisés, et rien ne remplit `valeur_quotidienne` : voir « rendement pondéré par les
   apports » ci-dessous.

Reste à faire pour le dashboard professionnel :

- **Courbe face à « acheter et garder »** : la courbe montre le résultat net réalisé cumulé, sans
  point de comparaison. `mesures.ecart_au_benchmark` existe, mais demande une valeur quotidienne
  du compte et une série de référence.
- **Rendement pondéré par les apports** : rendement, drawdown, Sharpe et Sortino ne sont pas
  affichés, faute de valeur quotidienne du compte nette des dépôts et retraits.
- **Devise par instrument** : la devise d'un titre vient du relevé (compte réel) ou du suffixe du
  ticker (compte paper). Indices hors États-Unis et paires de change non cotées en dollars
  restent en USD par défaut (liste dans `docs/SOCLE_JOURNAL.md`, lot 3). Une devise autre que
  l'euro et le dollar n'est pas convertie : la page écrit « devise non convertie ».
- **Pages suivantes** : Agent, Risque, Coûts, Analyse, Marchés, Système.

Points nés des pages :

- **CDN de `base.html`** : les pages `/pro` n'ajoutent aucun appel externe (courbes en SVG écrit
  par le serveur), mais elles héritent de `base.html`, qui charge Tailwind et Chart.js depuis deux
  CDN, comme les 14 autres pages. Sans Internet, leur mise en page se dégrade. À décider pour
  tout le dashboard : servir ces deux fichiers depuis `dashboard/static/`.
- **Types du relevé** : seuls DIVIDEND, CASH TOP-UP et CASH WITHDRAWAL, au type exact, deviennent
  des mouvements. Un type voisin (retenue ou correction sur dividende, frais de garde, division
  d'actions) reste ignoré et compté : à trancher sur un vrai relevé.
- **Dépôt ou dividende négatif** : l'import entier est refusé, avec le numéro de la ligne. Si un
  vrai relevé contient une telle ligne (annulation), décider comment l'enregistrer.
- **Bouton « Synchroniser » sans réseau** : si le taux EURUSD est indisponible, rien n'est écrit,
  positions paper comprises. Les scripts permettent de faire l'un sans l'autre. Les cours de
  clôture viennent ensuite, à part : leur échec n'annule rien.
- **Durée de la synchronisation** : les cours sont demandés à Yahoo un instrument après l'autre.
  Le premier passage télécharge tout depuis le premier trade de chaque instrument ; les suivants,
  7 jours. À regrouper en une seule requête si le clic devient trop long.
- **Symboles du relevé chez Yahoo** : le symbole du grand livre est demandé tel quel. Un titre
  Revolut coté ailleurs qu'aux États-Unis aura besoin d'une correspondance ; d'ici là il est
  listé « introuvable » et son résultat latent reste « prix indisponible ».
- **Marquage des boucles avant la synchronisation** : une position ajoutée après le dernier
  `scripts\marquer_boucles.py --appliquer` vaut 0 dans la colonne `boucle`. Le bouton ne relance pas
  le marquage (il écrirait dans la base de l'agent).
- **Date du correctif du prix d'entrée** : constante `CORRECTIF_PRIX_ENTREE`
  (`dashboard/pro/donnees.py`), lue une fois dans la base de la tour d'après la règle du registre
  (§9.4). Le grand livre ne garde pas le mécanisme d'entrée de chaque position.
- **Dernier prix** : le cours du grand livre (table `cours`, remplie par « Synchroniser » ou
  `scripts/ledger_cours.py`), sinon `prices`, que la collecte ne remplit que pour la watchlist. Si
  le grand livre a un cours trop vieux pour un titre, la base de l'agent n'est pas consultée : il
  faut resynchroniser. L'âge se compte du lundi au vendredi, sans calendrier des jours fériés.
- **Cours et devise** : un cours est enregistré dans la devise de l'instrument du grand livre, y
  compris quand cette devise est incertaine (indices hors États-Unis en USD par défaut).
- **Accès** : comme le reste du dashboard, ces pages n'ont pas d'authentification ; tout appareil
  du tailnet peut importer un relevé ou lancer la synchronisation.
- **Navigation** : 15 entrées dans la barre du bas, serrée sur téléphone.

Points nés de l'intégration du socle :

- **Devise incertaine** : le rapport de la synchronisation nomme les tickers enregistrés en USD
  par défaut. Une devise fausse se corrige par `corriger_trade(devise=...)`.
- **1 € = 1 $ dans le paper trader** (§29) : le grand livre enregistre la devise de cotation, mais
  les tailles des positions ont été calculées en prenant des euros pour des dollars. Les montants
  du grand livre et `pnl_euros` de la table `positions` ne se comparent donc pas directement.
- **Résultats paper bruts de frais** : aucun coût inscrit pour ces trades ; la page affiche « — »
  pour le total des frais et pour leur part, et la mention reste visible sur le panneau paper.
- **Topologie** : `ledger/`, `mesures/` et `importeurs/` restent classés avec les outils
  (composant masqué de la page Architecture), bien que `dashboard/pro/` les lise désormais ; les
  modules de `dashboard/pro/` sont dans le composant Dashboard.

## 45. Rejeu sur plusieurs années : points ouverts

Rejeu du cœur technique ajouté le 24/11/2026 (`rejeu/`, `docs/REJEU_JOURNAL.md`, critère au registre
§10). Aucun point ci-dessous ne change une décision de l'agent.

- **Frais « Revolut »** : 1 € par ordre vient d'un relevé ; à confirmer contre la grille tarifaire.
- **Frais « CFD »** : écarts et financement sont des hypothèses ; à remplacer par des écarts mesurés
  sur un compte démo. Les contrats à terme ont reçu l'écart des cryptos, faute de consigne.
- **Biais de sélection** : l'univers est la liste de 2026. Un rejeu sur un univers figé à une date
  passée (titres disparus compris) reste à faire.
- **Analystes neutralisés** : fondamental, sentiment, Fear & Greed, mémoire et intuition n'ont pas
  d'historique daté ; le rejeu ne dit rien de leur apport.
- **Barres quotidiennes** : une décision par jour, exécution à l'ouverture suivante. L'agent réel
  décide aussi toutes les 15 minutes : non rejoué.
- **Capital constant** : comme en production, l'agent dimensionne ses positions sur un capital qui
  ne suit pas le résultat (voir le lot comportement, point 1) ; le rejeu ne l'arrête pas quand le
  compte passe sous zéro.
- **Ventes à découvert** : gardées dans tous les profils ; un compte d'actions au comptant ne les
  permet pas.
- **Réglages de la tour** : le rejeu teste les défauts de `config.py` (5 positions simultanées),
  pas le `.env` de la tour (20).
- **Relance** : `scripts/rejeu_donnees.py --rafraichir` change les barres, donc le résultat ; à ne
  faire qu'en le notant au journal.
- **Change** : 1 € = 1 $, comme le paper trader (§29).

## Entrées sorties le 23/11/2026

Le détail de chaque entrée reste dans l'histoire git de ce fichier.

| § | Entrée | Close par |
|---|---|---|
| tête | Décisions du cycle tactical persistées nulle part | Registre R2 (06/10/2026), `utils/registre_cycles.enregistrer_decisions` ; reliquat au §26 |
| 1 | Rotation des logs cassée (Windows) | 16/10/2026, `utils/logger.py` et `utils/journal_rotation.py` ; reliquat au §43 |
| 6 | Piste quota LLM : l'audit métacognitif des cycles | Éteint par défaut depuis Q1 ; retrait du code au §43 |
| 9 | Conseils réels tronqués, stockés tels quels | 17/10/2026, `agents/real_advisor.py` |
| 10 | Code mort : anciens skills et visualizer | 16/10/2026 ; `agents/backtester/` supprimé le 23/11/2026 |
| 11 | Rupture de série des données de prix du 06/10/2026 (P9, P10) | Note portée par `docs/REGISTRE_CRITERES.md` |
| 13 | Interventions manuelles du dashboard non enregistrées | R3, `utils/registre_manuel.py` ; deux des trois routes retirées le 23/11/2026 |
| 15 | `_seuil_confiance_requis` calculé, jamais appliqué | Supprimé le 23/11/2026 : lu par aucun code |
| 16 | La page Settings réordonne la watchlist | P14, `dashboard/api/watchlist_io.py` |
| 18 | Le cycle stratégique ne traite pas la queue | 17/10/2026, documentation alignée sur le code |
| 19 | Les explorateurs tournent deux fois | 17/10/2026, retirés du stratégique |
| 23 | Observation Jev : activation sur la tour | Critère commité (registre §7) ; première observation le 09/10/2026 ; `jev_essai.py` au §43 |
| 24 | Statistiques de performance fictives jusqu'au 08/10/2026 | Note portée par `docs/REGISTRE_CRITERES.md` |
| 28 | Suites de tests Jev qui écrivaient dans `logs/` | 16/10/2026, `tests/journaux_isoles.py` |
| 30 | Contrôles des plans réels hors de tout cycle | 17/10/2026, `agents/plans_quotidien.py` |
| 34 | Dashboard arrêté sans alerte | Tâche `\AlphaSignal\surveillance` installée (`scripts/surveiller_dashboard.py`). Relance manuelle sûre : arrêter le processus qui écoute sur le port, attendre que la tâche `dashboard` ne soit plus « Running », puis `Start-ScheduledTask` |
| 35 | Position réelle sans prix comptée comme une perte totale | 14/10/2026, `utils/real_vue.py` et `utils/real_conversion.py` ; reliquat au §32 |
| 36 | Plan sans position : un P&L de 0 affiché | 16/10/2026, `utils/real_conversion.py` |
| 37 | Clés d'API en clair dans les logs | 19/10/2026, `utils/secret_mask.py` ; reliquats au §43 |
| 38 | Journal d'intuition jamais écrit | 19/10/2026, `journaliser_intuition` (`agents/intuition.py`) |
| 39 | `memory/` hors du suivi git | 19/10/2026 ; `ajouter_lecon` supprimée le 23/11/2026 |
| 40 | Positions « boucle » : périmètre de l'interrupteur | 21/10/2026 (registre v1.9 §9.5) ; interrupteur toujours à 0, voir la section de tête |
| 41 | Collecte des prix du 17/10 jamais faite | 19/10/2026, `utils/collecte_verifiee.py` et `utils/alerte_routine.py` |
