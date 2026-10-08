# TODO — hors périmètre

Points relevés pendant la Phase 4 (audit du chat stratégique, 01/10/2026).
Non traités : chacun fera l'objet d'un travail séparé.

## ⚠️ PRIORITÉ HAUTE — Décisions du cycle tactical persistées nulle part

- `scripts/cycle_tactical.py:63-74` : `decider()` tourne toutes les 15 min
  (queue ≤ 5 tickers + 8 tickers de la watchlist hors positions ouvertes).
  Les décisions restent en mémoire le temps d'`executer_ouvertures`, puis
  sont perdues : HOLD, NO_TRADE, et BUY/SELL refusés par le Budget Manager
  ne laissent aucune trace.
- Seule trace existante : la table `signals`, écrite par la routine
  quotidienne (un lot vers 07h40), uniquement pour les BUY/SELL validés
  par le Risk Manager.
- **Prérequis du registre de signaux.** Conséquence immédiate : le chat ne
  peut pas réutiliser une décision de cycle ; depuis E2 il calcule sa propre
  décision à la volée (`decider(..., origine="chat")`). Relevé le 03/10/2026,
  volontairement non traité dans E2.

## ⚠️ PRIORITÉ HAUTE — `signal_results` jamais alimentée en production

- Seul écrivain : `cloturer_signal()` (`agents/trade_journalist/journalist.py:97`),
  appelé uniquement par le bloc de démonstration `__main__` de
  `performance_tracker.py` (valeurs fictives BTC/ETH/AAPL). Les signaux de la
  routine quotidienne (`orchestrator.py:229`, `enregistrer_signal`) ne sont
  jamais clôturés. Relevé le 07/10/2026 (carte du code, Phase 3).
- Lecture statique : **des décisions lisent des statistiques issues de cette
  table** (jointure `INNER JOIN signal_results`) :
  - `utils/memory_lookups.py` (`winrate_par_actif`, `winrate_recent`,
    `pertes_consecutives_recentes`, `setups_similaires`) → contexte du pipeline
    groupé (`agents/skills/_memory_context.py` → `pipeline_grouped.py`), donc
    coefficient de taille des BUY/SELL ;
  - `performance_tracker.stats_par_actif` / `calculer_stats_globales` →
    `mettre_a_jour_performance_md()` (routine quotidienne) →
    `memory/performance_tracker.md` → `memory_reader.lire_winrate_par_actif` →
    override « track record défavorable » (`decision_engine.py:82`),
    `_seuil_confiance_requis` (§15), intuition (`agents/intuition.py`), et
    `winrate_historique` du Budget Manager (`paper_trader/cycle.py:50`,
    allocation) ;
  - `verifier_alerte_degradation` (email « dégradation perf ») et le contexte
    du chat (`calculer_stats_globales`).
- **À vérifier demain sur la tour, avant tout autre travail sur ce point**
  (lecture seule) :
  - `SELECT COUNT(*) FROM signal_results` et le contenu : vide, ou seulement
    les lignes de démonstration / de test (`scripts/nettoyer_signaux_test.py`) ?
  - contenu de `memory/performance_tracker.md` (table « Performance par
    actif ») : vide, données de démonstration, ou autre source ?
  - dans le registre, des décisions dont l'override « track record » ou
    l'intuition a joué, et le `winrate_historique` transmis au Budget Manager
    (50 par défaut si inconnu).
- Si la table est vide : ces décisions reposent sur une table vide (winrate
  inconnu, overrides jamais déclenchés, 50 % par défaut). Si elle ne contient
  que des lignes de démonstration : elles reposent sur des **données
  fictives**, ce qui est pire. Ne rien corriger avant ce constat.

## 1. Rotation des logs cassée (Windows)

- Les cycles et le dashboard écrivent tous dans `logs/alphasignal.log` et
  `logs/errors.log` via `RotatingFileHandler` (`utils/logger.py`). La
  rotation échoue : `PermissionError: [WinError 32]`, le fichier est
  ouvert par un autre processus.
- Le fichier n'est jamais renommé, donc chaque nouvelle ligne de log tente
  une rotation, échoue et déverse une trace « --- Logging error --- » sur
  stderr, redirigée dans `logs/task_*.log`.
- Au 01/10/2026 : `alphasignal.log` n'est plus écrit depuis le 25/09,
  `errors.log` depuis le 26/09, `task_tactical.log` atteint 529 Mo.

## 2. Classement des erreurs LLM par sous-chaîne

- Groq (`utils/llm.py::_try_groq`) : `"429" in err or "rate" in err` →
  `rate_limit_groq`, avec retry dans 60 s.
- L'erreur brute est maintenant visible dans `message_audit.chaine_de_fallback`.
  Le 01/10 (enregistrement #2), elle montre que le 429 venait du **quota
  quotidien de tokens** (TPD : 200 000/jour, 199 997 utilisés), pas d'une
  limite par minute. Le délai de 60 s est donc faux, et c'est le budget
  quotidien que les cycles consomment.
- Gemini suit le même schéma (`utils/gemini.py`, `ask_gemini` et
  `ask_gemini_status` : « 429 », « rate », « quota »). En plus,
  `ask_gemini_status` remplace le message d'origine par un texte fixe pour
  toutes les catégories connues : l'audit ne voit l'erreur brute de Gemini
  que pour les erreurs « inconnu ».
- **Gemini corrigé en Q5 (06/10)** : « freetier » figurait dans les 429 par
  jour ET par minute (41 965 « PerDay » et 36 « PerMinute » dans les logs,
  tous comptés en quota quotidien). Classement désormais d'après le quotaId
  (`utils/gemini_erreurs.py`), `429_inconnu` sans identifiant, message brut
  masqué dans les logs et l'audit. Limites lues dans les réponses de Google :
  20 requêtes/jour et 5/minute (quotaValue). Remise à zéro quotidienne : les
  retryDelay longs (> 1 h) pointent tous vers 01h00 heure de Lisbonne (minuit
  UTC), mais certains 429 « par jour » n'annoncent que quelques secondes, et
  Gemini a répondu au chat le 06/10 à 16h04 après un « par jour » à 07h32 :
  à confirmer avec les messages bruts désormais journalisés. Groq reste à
  corriger.

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

## 6. Piste quota LLM : l'audit métacognitif des cycles

- `agents/decision_engine_meta.py::audit_metacognitif` fait un appel Gemini
  direct pour chaque décision sauf HOLD (BUY, SELL et NO_TRADE ; cycles et
  conseiller réel). Son résultat (`resultat["metacognition"]`) n'est lu par
  **aucun code** et n'est sérialisé nulle part : il ne change ni l'action ni
  la taille. (Correction du 05/10 : `decision_formatter` lit le verdict
  métacognitif du *pipeline*, `pipeline_raisonnement["metacognition"]`, pas
  celui-ci.)
- **Mesurer d'abord** combien d'appels par jour il représente (et leur part
  du quota Gemini de 20 requêtes/jour) avant de décider quoi que ce soit.
- Mesuré le 05/10 : ≈ 565 appels/jour, tous en échec hors de la fenêtre de
  08h00. **Désactivé par défaut depuis Q1** (`METACOG_AUDIT_ENABLED=false`).

## 7. `POST` et `PUT /api/plans` ne sont pas plafonnés

- E4 plafonne uniquement le mode plan du chat (`agents/chat/plan_builder.py`,
  règle dans `agents/chat/_plan_budget.py`).
- `POST /api/plans` (création) et `PUT /api/plans/<id>` (`modifier_plan` :
  budget en €, pourcentage, statut…) n'appliquent aucun plafond. Aucune
  interface ne s'en sert pour le budget aujourd'hui (le formulaire d'édition
  de la page Plans ne touche ni budget, ni pourcentage, ni statut), mais ils
  sont joignables sans authentification depuis le tailnet.

## 8. JUSTESSE — P&L latent inconnu présenté comme 0 au LLM du chat

- Le chat construit son contexte avec `etat_portefeuille(with_live_prices=False)`
  (`agents/chat/context_builder.py`) : aucune position n'a de prix, donc
  `prix_actuel` et `unrealized_pnl_euros` valent `null` pour toutes.
- `agents/paper_trader/portfolio.py:95` fait
  `sum(p.get("unrealized_pnl_euros") or 0 …)` : l'inconnu devient **0**, et
  `total_value` = capital + 0.
- Le prompt annonce alors « P&L latent : +0.00€ » (constaté dans
  `message_audit` n°13, 03/10 : 11 positions, 11 `prix_actuel` à null) : un
  chiffre inconnu est présenté comme un zéro factuel.
- **Corrigé pour le chat (06/10)** : `portfolio.prix_actuel` dépose chaque prix
  relevé par les cycles dans `data/cache/dernier_prix/` (`utils/dernier_prix.py`,
  sans appel réseau en plus) ; le chat valorise les positions à ce prix s'il a
  moins de `CHAT_PRIX_AGE_MAX_MIN` (30 min), indique son heure et la couverture
  (« sur 8 positions sur 13 »), sinon « non disponible ».
- Reste à traiter (relevé dans l'inventaire du 06/10, non corrigé) :
  - ~~**Dashboard, page Overview**~~ : **corrigé le 06/10/2026**. `/api/portfolio`
    (`dashboard/api/queries.py`) valorise les positions au même cache de prix,
    avec la règle du chat (couverture, heure des prix, « non disponible » ;
    somme partielle signalée, jamais présentée comme le total).
    `etat_portefeuille` et les cycles inchangés.
  - **P&L réalisé réel** : `utils/real_portfolio_db.py:486` compte 0 pour une
    position réelle close sans `realized_pnl` (aucune au 06/10).
  - **Mode défensif** : `agents/paper_trader/portfolio.py:41` compte un P&L
    inconnu comme « pas une perte » (fonction partagée avec la gestion du risque
    des cycles ; aucune position close sans P&L au 06/10).
  - **Défaut inverse** (`agents/chat/_extraction.py`) : une perf. 1 mois de
    0,0 % devient `None` (`:151`, test `if change_1m`), un RSI sans aucune baisse
    devient `None` au lieu de 100 (`:135`).

## 9. Conseils réels tronqués, stockés tels quels

- `agents/real_advisor.py::_enrichir_llm` remplace la justification d'un
  conseil par le texte du LLM, appelé avec `max_tokens=200`
  (`real_advisor.py:76-80`), sans vérifier que la phrase est complète.
- Exemples dans `real_advice_log` (03/10 vers 07h05) : n°2518 « VRT est en
  ligne avec », n°2515 « Maintenez la position MU, ». Ces textes sont
  affichés tels quels dans « Conseils en attente » (page Réel).

## 10. Code mort à supprimer : anciens skills et visualizer (commit de nettoyage séparé)

- `agents/skills/pipeline.py` n'est importé par aucun module (remplacé par
  `pipeline_grouped.py`). Il est le seul à importer `bayesien.py`,
  `base_rates.py`, `metacognition.py`, `pre_mortem.py` et `second_ordre.py`,
  qui appellent `ask_gemini` en direct, hors de la réserve Gemini (Q4).
- Relevé le 06/10/2026 pendant Q4 : 0 appel en production. Ne pas les
  rebrancher tels quels ; vérifier les imports avant suppression.
- **`agents/skills/__init__.py` importe aussi les 5 skills** (ligne
  `from agents.skills import bayesien, pre_mortem, ...` + `__all__`) : tout
  import de `agents.skills.pipeline_grouped` ou `pipeline_cache` les charge,
  sans jamais les appeler. La suppression doit retirer cette ligne et
  `__all__` (et la docstring qui les présente), sinon le paquet ne s'importe
  plus et `pipeline_grouped` casse. Confirmé par Graphify le 07/10/2026 :
  `pipeline.py` n'a aucune arête entrante ; les 5 skills n'en ont que depuis
  `pipeline.py` et `__init__.py`.
- **`agents/backtester/visualizer.py`** (graphiques equity/drawdown en PNG
  vers `strategies/backtest_results/`) : importé par aucun module, ni
  aujourd'hui ni dans l'historique git (`git log -S` : seul le commit initial
  v4.1 du 04/05/2026 le mentionne). À supprimer dans le même commit de
  nettoyage. Attention : il crée `strategies/backtest_results/` à l'import
  (`os.makedirs` au niveau module), sans effet puisqu'il n'est jamais importé.
- Le Sentiment Analyst (`sentiment_analyst/_llm.py`) garde lui aussi
  `ask_gemini` en direct : laissé volontairement, il n'est appelé que par
  le bloc `__main__` d'`analyst.py` (lancement manuel).

## 11. ⚠️ Rupture de série des données de prix — 06/10/2026 (P9 et P10)

- Le 06/10/2026, P9 a réparé 42 barres journalières à prix NULL (actions et
  ETF, juin et août) et P10 a remplacé environ 1 500 barres enregistrées avant
  leur clôture puis figées (journalières des cryptos et des futures, quelques
  actions des 23-24/09, hebdomadaires de tous les actifs, horaires des cryptos).
- Les indicateurs changent (ATR des cryptos +18 à +40 %, futures +12 à +20 %),
  ainsi que les stops et une partie des signaux : sur les 119 signaux émis
  depuis le 28/09, rejoués sans réseau, 23 signaux techniques diffèrent
  (12 crypto, 3 futures, 8 actions).
- **Les résultats paper d'avant et d'après le 06/10/2026 ne sont pas
  comparables** (winrate, P&L, performance par actif, intuition) : ils
  reposent sur des données corrigées. Ne pas les agréger sans le signaler.

## 12. R:R structurellement constant à 2.0

- `calculer_targets` (`agents/analysts/risk_manager/position_sizer.py:41`)
  place l'objectif 1 à 2 × la distance du stop : le R:R de l'objectif 1 vaut
  toujours 2.0 (741 signaux sur 741 au 06/10/2026, avant comme après P10).
- Le filtre du Risk Manager (`R:R < RR_MINIMUM` = 1.2,
  `agents/analysts/risk_manager/manager.py:23` et `:109`) ne peut donc rejeter
  que des données manquantes (depuis P9 : « Données de prix manquantes ») ;
  il ne filtre aucun trade sur sa qualité.
- Décision de conception à prendre plus tard (par exemple un objectif fondé
  sur les niveaux de marché, ou la suppression de ce filtre).

## 13. Registre : interventions manuelles depuis le dashboard non enregistrées (à faire en R3)

- Depuis R2 (06/10/2026), le registre (`data/registre.db`) enregistre les
  décisions et les événements de position des cycles, mais pas les actions
  manuelles faites depuis le dashboard. **Facteur de confusion pour les
  analyses R4** : une position dont le comportement a été modifié à la main
  serait comptée comme une décision des cycles.
- Routes concernées (`dashboard/api/routes.py`, inventaire au 06/10/2026) :
  - `POST /api/positions/<id>/trailing-stop` (`:127`) : active ou désactive le
    trailing stop d'une position paper. Les déplacements du stop qui suivent
    sont enregistrés par les cycles (`STOP_DEPLACE`), pas l'activation ;
  - `POST /api/run-analysis` (`:557`) : lance la routine quotidienne dans le
    processus du dashboard. Elle est enregistrée comme un passage
    `quotidien` ordinaire, et ses ouvertures de positions avec ; à distinguer
    (cycle `manuel` ou origine `dashboard`) ;
  - `POST /api/settings/watchlist` (`:571`) : change les actifs analysés ;
    la watchlist ne fait pas partie de l'empreinte des paramètres. **En R3,
    la composition de la watchlist doit entrer dans l'empreinte des
    paramètres** (`parametres_actifs`, `utils/registre.py`) : un changement
    de watchlist crée alors une nouvelle ligne `parametres`. Au 06/10/2026,
    cette route est le seul code qui écrit `data/watchlist.json` ; les
    explorateurs alimentent la queue, pas la watchlist (CLAUDE.md dit
    « élargie automatiquement par les 7 explorateurs »).
  - Toute route ajoutée plus tard qui modifie une position paper.
- Le cycle `manuel` est déjà admis par le schéma (CHECK de
  `utils/registre_schema.py`, ajouté avant la première écriture pour éviter
  une migration). Reste à brancher les routes en R3.
- **Fait en R3** (`utils/registre_manuel.py`) : les trois routes ci-dessus
  ouvrent un passage `manuel` avec leur déclencheur (trailing stop : ligne
  `TRAILING_ACTIVE` ou `TRAILING_DESACTIVE` ; run-analysis : décisions de la
  routine ; watchlist : actifs ajoutés, retirés, ordre modifié). La
  composition de la watchlist (ordre compris) entre dans l'empreinte des
  paramètres. Inventaire du 06/10/2026 : aucune autre route ne modifie une
  position paper.
- Non enregistrées (hors périmètre paper) : les routes du portefeuille réel
  (`/api/real/*`, `/api/plans/*`, `/api/chat/create-plan`). Elles changent les
  positions évaluées par le conseiller, dont les décisions sont au registre
  (origine `conseiller`).

## 14. Découvertes des explorateurs jamais analysées faute de prix

- Le tactical analyse à chaque passage les 5 premières entrées de la queue
  (`scripts/cycle_tactical.py`, étape 3). Les indicateurs ne lisent que la
  table `prices`, qui ne contient que les 23 actifs de la watchlist (seule
  la watchlist est collectée par `scripts/fetch_data.py`), et les
  explorateurs excluent la watchlist de leur scan (`agents/explorers/base.py:67`) :
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
      (CLAUDE.md, CLAUDE.md des explorateurs) à aligner.
    - Effet : environ 3 s gagnées par passage, 5 recherches de news en moins
      par passage (NewsAPI est déjà saturé : 742 réponses 429 dans le log du
      tactical le 06/10), environ 450 lignes vides en moins par jour dans le
      registre. Aucun effet sur les trades : faute de prix, la queue ne peut
      ouvrir aucune position aujourd'hui. Les explorateurs ne servent plus qu'aux alertes email
      (score ≥ 7) ; leurs découvertes ne sont jamais évaluées.

## 15. `_seuil_confiance_requis` calculé mais jamais appliqué (code mort ou oubli ?)

- `agents/decision_engine.py:101` : `_seuil_confiance_requis(analyses)` renvoie 9
  si l'actif a au moins 3 trades et un winrate sous `WINRATE_PRUDENCE` (35 %),
  sinon 7. `decider()` le calcule (`:124`) et le renvoie dans
  `seuil_confiance_requis` (`:189`), mais **aucun filtre ne le lit** (relevé
  le 06/10/2026, P13).
- Les filtres réellement appliqués sont le pré-filtre du Budget Manager
  (`confiance_min` du mode) et la porte du Paper Trader
  (`SEUIL_CONFIANCE_PAPER`, 8 ; 9 après 3 pertes d'affilée ;
  `SEUIL_CONFIANCE_LEARNING`, 4).
- À trancher : l'intention était-elle d'exiger 9 sur un actif au mauvais
  winrate ? Si oui, c'est un oubli et le brancher changerait des décisions
  (décision séparée, à évaluer avec REGISTRE_CRITERES) ; sinon, le supprimer.

## 16. La page Settings réordonne la watchlist (ordre alphabétique)

- `GET /api/watchlist` renvoie la watchlist par `jsonify`, et Flask trie les
  clés (`DefaultJSONProvider.sort_keys = True`, Flask 3.1.3). La page Settings
  garde cet objet trié et le renvoie en entier à chaque clic sur un actif
  (`toggleAsset`, `POST /api/settings/watchlist`) : `data/watchlist.json` est
  alors réécrit dans l'ordre alphabétique (catégories et tickers).
- Effet : le tactical n'analyse que les 8 premiers actifs hors positions
  ouvertes (`scripts/cycle_tactical.py`, étape 4). Un simple clic change donc
  les actifs analysés. Relevé le 06/10/2026 (R3) ; le fichier est encore
  identique à sa version commitée du 19/06 (a404ac6), dans son ordre d'origine.
- Depuis R3, un tel changement est visible : passage `manuel` avec
  `ordre_modifie`, et nouvelle ligne `parametres` (l'ordre fait partie de
  l'empreinte).
- À décider : garder l'ordre du fichier (réponse sans tri pour cette route,
  ou renvoi du seul changement), ou rendre la sélection du tactical
  indépendante de l'ordre.
- **Corrigé en P14** (ordre du fichier gardé ; `dashboard/api/watchlist_io.py`) :
  `GET /api/watchlist` répond sans tri ; la page Settings n'envoie plus que
  l'actif cliqué (`POST /api/settings/watchlist/actif`), dont seul le booléen
  `actif` change, sur sa ligne ; `POST /api/settings/watchlist` (page
  ancienne restée ouverte, autre client) garde l'ordre du fichier existant.
  La sélection des 8 actifs du tactical dépend toujours de cet ordre, qui ne
  change plus que par une édition volontaire du fichier.

## 17. Fonctionnalités annoncées mais jamais appelées : brancher ou supprimer ?

Relevé le 07/10/2026 avec Graphify (modules sans aucune arête entrante),
confirmé par grep et par `git log -S` sur tout l'historique : **aucun de ces
modules n'a jamais été importé** depuis son ajout. Ce n'est pas une régression,
ils n'ont jamais été branchés. Ne rien supprimer avant décision.

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

## 18. Le cycle stratégique ne traite pas la queue

- `scripts/cycle_strategic.py` : sa docstring annonce « Lance les 7
  explorateurs + traite la queue (analyses complètes) ». En réalité il lit la
  queue seulement pour en journaliser la longueur (`lire_queue()`, puis
  `logger.info(... queue à N actifs)`) ; il n'importe ni `asset_analyzer` ni
  `decision_engine`. Relevé le 07/10/2026 (carte du code, Phase 3).
- Seul le tactical analyse la queue (5 entrées par passage, puis retirées).
- À décider : corriger la docstring (et CLAUDE.md), ou lui faire réellement
  analyser la queue (sans effet tant que §14 n'est pas réglé : les tickers de
  la queue n'ont pas de prix).

## 19. Les explorateurs tournent deux fois

- Le tactical (toutes les 15 min, `_lancer_explorateurs`, import dynamique
  par nom de module) **et** le stratégique (toutes les 4 h) lancent les mêmes
  7 explorateurs. Le passage de 4 h n'apporte rien de plus : la queue est déjà
  alimentée toutes les 15 min. Coût : un scan complet (~180 actifs, 6 mois de
  barres journalières par actif) en plus toutes les 4 h, sur Yahoo déjà en 429.
- Seule différence relevée : `CryptoExplorer(nb_max=50)` dans le stratégique.
- À décider : retirer les explorateurs du stratégique, ou les retirer du
  tactical et garder un rythme de 4 h (ce qui changerait la fraîcheur des
  découvertes).

## 20. L'intuition force BUY après un veto, y compris sur un signal baissier

- `agents/intuition.py:478-480` : si la décision provisoire est `NO_TRADE`
  (donc après **n'importe quel** override de `_verifier_overrides` :
  veto du Risk Manager, Fear & Greed extrême) et que `ajustement ≥ 2`,
  l'intuition renvoie `override_decision = "BUY"`. `decider()` l'applique
  (`agents/decision_engine.py:163-169`) en style `learning` (×0.2, seuil de
  confiance 4). Le veto est levé **et la direction peut être inversée** :
  un signal technique VENTE bloqué devient un achat. Relevé le 08/10/2026.
- En pratique, `ajustement ≥ 2` demande un winrate ≥ 70 % sur ≥ 3 trades et
  au moins un pattern trouvé dans `market_patterns.md` (le pilier
  géopolitique ne contribue jamais, `actifs_a_surveiller` n'étant jamais
  placé dans `context`). Le veto « track record » ne peut pas être levé
  (winrate < 35 % donne déjà -2). Le veto Risk Manager est re-validé par le
  Paper Trader (`agents/paper_trader/cycle.py:82`), mais en LONG avec le
  budget alloué, donc sur une autre question que celle rejetée.
- Note : la docstring `agents/intuition.py:425` est fausse. `ajustement` y est
  décrit comme « à ajouter au score composite » ; `decider()` ne l'ajoute
  jamais au score, il ne sert qu'au seuil d'override et au pressentiment.
- **Critère à pré-enregistrer avant correction** (REGISTRE_CRITERES) : ce
  qui serait mesuré (rendement des BUY issus d'un override intuitif après
  `NO_TRADE`, comparés à leur absence), sur quel horizon, avec quel seuil.
  Ne rien corriger avant.

## 21. Veto Extreme Greed contournable (quotidien) et inactif (tactical)

- Cycle quotidien : `_verifier_overrides` (`agents/decision_engine.py:88-96`)
  bloque un achat si F&G ≥ 80. L'intuition (§20) peut lever ce `NO_TRADE` en
  BUY, et **rien ne revérifie le F&G en aval** (le Paper Trader ne re-valide
  que le risque) : on peut acheter exactement dans le cas que le veto devait
  empêcher.
- Tactical : `scripts/cycle_tactical.py:67` appelle
  `analyser_actif_complet(t)` sans `sentiment_global`, donc `context` n'a pas
  de `fg_valeur` : l'override F&G (Extreme Fear comme Extreme Greed) **ne
  s'active jamais** dans le tactical, ni dans `reevaluer_position`. Les deux
  cycles appliquent donc des règles différentes au même actif. Relevé le
  08/10/2026.
- **Critère à pré-enregistrer avant correction** : transmettre le F&G au
  tactical ou fermer le contournement change des décisions ; décider d'abord
  ce qui serait mesuré, sur quel horizon, avec quel seuil.

## 22. Le tactical n'évalue que les 8 premiers actifs sans position

- `scripts/cycle_tactical.py:158-159` : `[:8]` sur la watchlist hors
  positions ouvertes. Dans l'ordre actuel du fichier, ce sont presque
  toujours BTC, ETH, SOL, HBAR, CRO, AAPL, TSLA, NVDA. `INDICES_US` (SPY, QQQ,
  VOO, NQ=F, rangs 18 à 22 sur 23) n'est atteint que si au moins 10 actifs
  placés avant ont une position ouverte ; `SEMIS_IA` se réduit à NVDA.
  Voir aussi §16 (la sélection dépend de l'ordre du fichier). Relevé le
  08/10/2026.
- Conséquence : les groupes de REGISTRE_CRITERES §0.1 sont très déséquilibrés
  dans les décisions du tactical, ce qui biaise la lecture Q3.a (couples
  examinés par le pipeline, majoritairement issus du tactical).
- **Critère à pré-enregistrer avant correction** : changer la sélection
  (rotation, tirage, tous les actifs) change les décisions et la composition
  des données Q3 ; fixer d'abord la règle et sa date d'effet dans
  REGISTRE_CRITERES.
