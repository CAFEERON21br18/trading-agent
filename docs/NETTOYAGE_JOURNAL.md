# Journal du nettoyage — TradingX / AlphaSignal

- Début : 23/11/2026. Branche `nettoyage-public`, partie de `38300ca` (= `origin/nettoyage`).
- Source : `docs/NETTOYAGE_INVENTAIRE.md` ; les numéros (1.1, 2.6, 7.4…) renvoient à ses lignes.
- Règle centrale : aucun retrait ne change une décision de l'agent (score, seuil, taille de
  position, ordre paper, écriture du registre). Un retrait qui le pourrait n'est pas fait : il est
  noté ici.
- Tests : `.venv\Scripts\python.exe -m unittest discover -s tests`, dans le worktree de la branche,
  réseau coupé (`HTTP_PROXY=HTTPS_PROXY=ALL_PROXY=http://127.0.0.1:9`). Le fichier
  `graphify-out/graph.json` (hors git) est absent du worktree : 10 tests de `tests/test_topology.py`
  sont ignorés, comme dans la référence.
- Référence de départ, relancée sur `38300ca` : `Ran 470 tests` / `OK (skipped=10)`.

## Lot 0 — Corrections urgentes

Parti ou corrigé :

- `.env.example` : `RISK_PER_TRADE_PCT=2` au lieu de 50 (8.26).
- `.env.example` : les 11 variables manquantes (8.27), avec la valeur par défaut du code :
  `GEMINI_API_KEY` et `GROQ_API_KEY` (vides), `MAX_CAPITAL_INVESTI_PCT=50`,
  `MAX_POSITIONS_SIMULTANEES=5`, puis en commentaire, comme les autres réglages optionnels du
  fichier : `SEUIL_CONFIANCE_PAPER=8`, `SEUIL_CONFIANCE_PAPER_DEFENSIF=9`,
  `SEUIL_CONFIANCE_LEARNING=4`, `ROTATION_ACTIVE=0`, `CHAT_HISTORIQUE=0`,
  `CHAT_HISTORIQUE_MAX_MIN=120`, `TAILSCALE_EXE_PATH` (chemin par défaut de `utils/tailscale.py:16`).
- `REPORT_TIME` retirée de `.env.example` et de `config.py` (8.28) : la constante n'était
  qu'affichée par `afficher_config()` ; la ligne affiche maintenant le fuseau seul.
- `CLAUDE.md`, règles absolues : règle 10, « Aucune ligne Co-Authored-By ni Claude-Session dans les
  messages de commit de ce dépôt. »
- `requirements.txt` : `matplotlib`, `plotly`, `schedule`, `pytz` retirées (10.1 à 10.4) ; `tzdata`
  ajoutée (10.6).

Resté :

- `MAX_POSITIONS_SIMULTANEES=5` dans le modèle est le défaut du code, comme demandé ; `CLAUDE.md`
  décrit 20, valeur du `.env` de la tour (non lu). L'écart est traité au lot 6 (8.16).
- La phrase « Laisser à 0 jusqu'au 28/10/2026 » de `.env.example` (8.12) attend la lecture de
  `EXCLURE_BOUCLES_STATS` (lots 5 et 6).

Tests : `Ran 470 tests` / `OK (skipped=10)`.

## Lot 1 — Code mort sans risque

Parti :

- 15 fonctions jamais référencées (1.19 à 1.31), chacune revérifiée avant le retrait par
  `git grep -w -n <nom>` → la ligne `def` seule : `recuperer_prix_dernier` (`macro.py`),
  `formater_section_budget` (`budget_manager/manager.py`), `formater_markdown`
  (`pretrade_analysis.py`), `_signal_depuis_analyses` (`orchestrator.py`), `reponse_vide`
  (`skills/_json_helper.py`), `lister_signaux_recents` (`journalist.py`), `ajouter_lecon`
  (`performance_tracker.py`), `recuperer_prix_coingecko` (`scripts/fetch_data.py`), `info_actif` et
  `recuperer_lot` (`utils/data_fetcher.py`), `lire_prix` (`utils/database.py`), `stats_usage`
  (`utils/gemini.py`), `cycles_actifs` (`utils/lock_manager.py`), `prix_actuel_calibre` et
  `get_display_entry_price` (`utils/real_price.py`).
- Ce que ces fonctions étaient seules à lire : `LESSONS_LEARNED_FILE` (`performance_tracker.py`) et
  sa redirection dans `demo_performance.py` ; `COINGECKO_URL`, `COINGECKO_IDS` et l'import
  `formater_prix` de `scripts/fetch_data.py`.
- `scripts/check_health.py` (1.2), copie exacte de `check_status.py`. L'en-tête de
  `check_status.py`, le message de panne de `scripts/daily_routine.py` et la docstring de
  `utils/scheduler_check.py` citent maintenant `check_status.py`.
- `main.py` (1.1), avec ses trois déclarations de point d'entrée (`scripts/graphify_modules.py`,
  `dashboard/api/etat_code.py`, `dashboard/api/topology_composants.py`), le paquet `main` de
  `tests/test_journaux_isoles.py`, et les mentions du `README.md` et de
  `docs/AVANT_ARGENT_REEL.md`.
- `CREATE TABLE` de `indicators` et de `sentiment` (4.1, 4.2) dans `utils/database.py`, et leurs
  deux entrées de `TABLES_CACHE` (`utils/audit_trace.py`). Aucune base existante n'est touchée :
  les tables déjà créées y restent.
- `NB_TRADES_DEFENSIF_RESET` (7.14) : `git grep -w` → sa définition seule.

Resté :

- 1.32, `get_real_budget_summary` et `progression_plan` : quatre modules de test s'en servent
  comme calcul de référence (consigne).
- `tests/test_topology.py` n'a pas eu besoin d'être modifié : aucun de ses tests ne cite `main.py`
  (le `main` de la ligne 90 est une fonction d'un dépôt fictif). Vérifié avec un graphe régénéré
  dans le worktree (`graphify extract . --code-only`, `Token cost: 0 input · 0 output`) : les
  18 tests du module passent, aucun n'est ignoré.
- Noms inutilisés qui existaient avant ce lot et ne sont pas à l'inventaire, laissés tels quels :
  `SERIES_FRED` (`macro.py`), `logger` (`pretrade_analysis.py`), `REQUEST_TIMEOUT_SEC`
  (`utils/gemini.py`), trois imports (`timedelta`, `timezone`, `datetime`).
- `docs/TODO.md` §34 cite encore `check_health.py` : l'entrée sort au lot 7.

À savoir après la fusion : `graphify-out/graph.json` de la tour contient encore `main.py` jusqu'à
la prochaine régénération (dimanche 20h, ou `scripts\regenerer_graphe.py`). D'ici là,
`test_tous_les_modules_classes` signalerait `main.py` comme non classé.

Tests : `Ran 470 tests` / `OK (skipped=10)` sans graphe ; `test_real_*` : 41 tests, OK.

## Lot 2 — macOS (Windows seulement)

Parti :

- Les 7 `scripts/com.alphasignal.*.plist`, `install_launchd.sh`, `uninstall_launchd.sh`,
  `install_v4.sh`, `run_mac.sh`, `backup_before_update.sh` (5.2) et `scripts/check_after_update.py`
  (1.4) : 13 fichiers.
- Ce qui les citait dans le code : la branche launchd de `scripts/check_status.py`
  (`_check_scheduler_launchd`, qui renvoyait vers `install_launchd.sh`) ; `check_scheduler` appelle
  maintenant le contrôle Windows sans condition. Le commentaire d'en-tête de
  `scripts/install_tasks_windows.ps1` ne cite plus `install_launchd.sh` (une ligne de commentaire ;
  aucune tâche planifiée n'est touchée).
- `scripts/daily_routine.py` : la docstring et la ligne de journal disaient « déclenchée par
  launchd » ; elles disent maintenant « lancement manuel » (la tâche `daily` lance
  `cycle_daily.py`).

Resté :

- `README.md`, `CLAUDE.md` et `docs/TAILSCALE.md` citent encore launchd et ces fichiers : ils sont
  réécrits au lot 6 (8.15, 8.19 à 8.25, 8.36).
- `docs/DIAG_PRIX_ENTREE.md:103` (« launchd sur macOS » avant le 23/09) : archive datée, laissée.
- Commentaires de portabilité sans lien avec les fichiers supprimés (`utils/lock_manager.py:27,31`,
  `dashboard/app.py:122`, section `# macOS` de `.gitignore`) : laissés.

Tests : `Ran 470 tests` / `OK (skipped=10)`.

## Lot 3 — Scripts ponctuels

Parti :

- `scripts/check_message_audit.py` (1.5), `scripts/reparer_barres_incompletes.py` (1.6),
  `scripts/reparer_prix_null.py` (1.7) : cités par aucun fichier, aucun test.
- `scripts/purger_signaux_demo.py` et `tests/test_purger_signaux_demo.py` (1.8, 11.3 ; 4 tests) :
  purge appliquée le 08/10.
- `scripts/migrer_devise_reelle.py` et `tests/test_real_devise_migration.py` (1.9, 11.4 ; 7 tests).
  Vérification préalable, base de la tour ouverte en lecture seule (`mode=ro`), structure
  seulement : `PRAGMA table_info(real_investments)` → la colonne `devise` est présente. Aucune
  valeur ni aucun nombre de lignes n'a été lu.
- `tests/test_fichiers_hors_git.py` (11.7) : le test des chemins ignorés par git prend le dossier
  des sauvegardes dans `scripts/marquer_boucles.py` (même dossier `data/sauvegardes/`), au lieu des
  deux scripts supprimés. Même nombre de tests dans ce fichier.
- `tests/test_real_devise.py` : il appelait `migration.migrer` pour créer la colonne dans sa base
  temporaire ; il exécute maintenant la même instruction `ALTER TABLE … ADD COLUMN devise` (comme le
  fait déjà `tests/test_plan_repartition.py`). Ce cas n'était pas à l'inventaire, qui ne citait que
  les 7 tests de la migration.
- Commentaires qui citaient les scripts supprimés : `.gitignore`, `demo_performance.py`,
  `utils/real_devise.py`, `tests/test_plan_repartition.py`.

Resté :

- `scripts/seed_plans.py` (1.10) et tous les scripts classés GARDER.
- `docs/TODO.md:94` cite `purger_signaux_demo.py` avec son commit, comme un fait daté : laissé.

À savoir : `initialiser_real_db` ne crée pas la colonne `devise` ; le script de migration était le
seul code qui l'ajoutait. Sur une base neuve, la colonne manque et `utils/real_devise.py` applique
la devise par défaut (USD), comme avant la migration. Le script reste dans l'histoire git ; la
docstring de `utils/real_devise.py` le dit.

Tests : `Ran 459 tests` / `OK (skipped=10)`. Les 11 tests en moins sont ceux des deux fichiers de
test supprimés (4 + 7).

## Lot 4 — Routes et analyses sans page

Contrôle préalable, refait sur l'arbre courant : aucun des chemins retirés n'apparaît dans
`dashboard/templates/` ni `dashboard/static/` (`grep -rn -i -E "attribution|backtest|stress-test|
catalyst|/regime|liquidity|api/intuition|trailing-stop|calibrate/|settings/watchlist\"|
api/positions/"` → rien). `dashboard/static/sw.js:3-9` ne met rien en cache : aucune ancienne page
ne peut appeler `POST /api/settings/watchlist`.

Parti :

- Modules : `agents/technical_skills/performance_attribution.py`, `backtester_pro.py`,
  `scenario_simulation.py`, `news_catalyst.py` ; `agents/backtester/` (`engine.py`, `metrics.py`,
  `CLAUDE.md`).
- Routes de `dashboard/api/routes.py` (11) : `/api/attribution`, `/api/backtest/<ticker>`,
  `/api/stress-test`, `/api/news-catalysts` (2.1) ; `/api/regime`, `/api/liquidity/<ticker>` (2.2) ;
  `/api/intuition` (2.3) ; `POST /api/positions/<id>/trailing-stop` (2.4) ;
  `GET /api/positions/<id>` (2.5) ; `POST /api/settings/watchlist` (2.6) ;
  `GET /api/real/calibrate/<ticker>` (2.7). Le fichier passe de 604 à 475 lignes.
- Ce que ces routes étaient seules à appeler : `noter_trailing` et son assistant `_position`
  (`utils/registre_manuel.py`), `position_detail` (`dashboard/api/queries.py`).
- Deux fonctions jamais appelées (1.34) : `evaluation_nouvelle_position` (`correlation.py`),
  `alerte_evenement_proche` (`economic_calendar.py`).
- Composant « Backtester » de la page Architecture (`dashboard/api/topology_composants.py` : sa
  ligne de `COMPOSANTS` et sa règle), et sa mention dans `utils/passage.py`.
- Tests ajustés, sans changer leur nombre : `tests/test_sources_passage.py` (11.5 : 12 composants
  au lieu de 13, plus d'appel à `agents.backtester.metrics`) ; `tests/test_dashboard_ecriture.py`
  (le plancher du nombre de routes modifiantes passe de 23 à 21 : les deux `POST` retirés).

Resté :

- `correlation.py` et `economic_calendar.py`, avec leurs routes `/api/correlation` et
  `/api/calendar` (consigne).
- Les modules `market_regime`, `liquidity` et la fonction `stats_intuition` : seules leurs routes
  partent.
- `utils/registre_manuel.py` garde les libellés `ROUTE_TRAILING` et `ROUTE_WATCHLIST` : d'anciennes
  lignes du registre les portent. `ROUTE_WATCHLIST` reste la valeur par défaut de
  `noter_watchlist` ; le seul appelant restant passe `ROUTE_WATCHLIST_ACTIF`.
- `activer_trailing_stop` et `desactiver_trailing_stop` (`agents/technical_skills/trailing_stop.py`)
  n'ont plus d'appelant : la route retirée était le seul. Elles ne sont pas à l'inventaire et
  touchent aux positions paper ; je les ai laissées. Le moniteur continue de suivre le stop des
  positions où `trailing_stop_active` vaut 1 ; plus rien ne peut mettre cette colonne à 1 ou à 0.
- `import subprocess` de `routes.py`, déjà inutilisé avant ce lot : laissé (le fichier est découpé
  au lot 8).
- `agents/technical_skills/CLAUDE.md` et `docs/TODO.md` citent encore les modules supprimés : le
  premier part au lot 6, les entrées du second (§10, §40) au lot 7.

Tests : `Ran 459 tests` / `OK (skipped=10)`. Avec un graphe régénéré dans le worktree :
`test_topology` → 18 tests, OK, aucun ignoré.

## Lot 5 — Code de décision sans effet

Constat qui encadre tout le lot : `utils/registre.py:72-97` (`parametres_actifs`) calcule l'empreinte
des paramètres écrite au registre à chaque passage. Elle contient `METACOG_AUDIT_ENABLED` (lu par
`getattr(config, …, None)`) et `MODES_BM`, le dictionnaire `PARAMETRES` de
`agents/budget_manager/strategy.py`, entrée `CONVICTION` comprise. Retirer l'un ou l'autre change
une écriture du registre : interdit par la règle centrale. D'où ce qui suit pour 7.2 et 7.9.

Deux contrôles communs, relancés après le lot :

- Empreinte de `parametres_actifs()` sur l'arbre de départ (`38300ca`) et sur l'arbre nettoyé, dans
  les mêmes conditions (sans `.env`, watchlist du modèle) : même SHA-256 (`e39a0f32…46c4`), mêmes
  26 clés, `erreur_lecture` absent.
- Sorties comparées sur 1 456 cas inventés et fixes (400 arbitrages de demandes construites par
  `creer_demande`, 1 056 appels de `consulter_intuition` sur une grille de mémoires, de contextes et
  de décisions) : même SHA-256 avant et après (`58b6d033…0a66`).

### 7.1 `budget_boost` — retiré

Preuve que le facteur vaut toujours 1.0 :

- Lecture unique : `arbitrator.py:27`, `demande.get("budget_boost", 1.0)`.
- `arbitrer` n'a qu'un appelant, `manager.traiter_demandes` ; qui n'en a qu'un,
  `paper_trader/cycle.py:71`, avec des demandes venues de `_decision_to_demande` → `creer_demande`
  (`git grep -n -E "creer_demande|traiter_demandes|arbitrer\("`).
- `creer_demande` construit un dictionnaire de 10 clés fixes, sans `budget_boost`
  (`manager.py:29-40`) ; rien n'ajoute de clé ensuite.
- Donc `boost` = 1.0, et `x * 1.0 == x` exactement en virgule flottante : le score est le même.
- La clé `budget_boost` de la décision (`decision_engine.py`) et de `noter_setup` n'a aucun lecteur :
  `resume_decision` (registre), `_resumer` (audit du chat), `context_builder` (chat), le pipeline et
  le formatage lisent des clés nommées, jamais celle-ci ; aucun code n'itère sur le dictionnaire.

Parti : le facteur dans `_calculer_score`, la clé dans `decider` (deux lignes) et dans
`noter_setup`, la constante `BUDGET_BOOST`.

### 7.2 Mode CONVICTION — branche retirée, entrée de `PARAMETRES` gardée

Preuve que la branche est inatteignable : `detecter_mode` est appelée sans argument partout
(`strategy.py:112,122`, `jev/observer.py:40`, `routes.py`, tests) sauf `manager.py:55`, qui
transmettait `conviction_force` de `traiter_demandes` ; or le seul appel est
`traiter_demandes(demandes)`. `conviction_force` vaut donc toujours `False`.

Parti : le paramètre `conviction_force` des deux fonctions et le `return "CONVICTION"`.

Resté, contre la lettre de la consigne : l'entrée `"CONVICTION"` de `PARAMETRES`. Elle entre dans
l'empreinte du registre (`MODES_BM`) ; la retirer changerait l'empreinte de chaque passage. Un
commentaire le dit dans `strategy.py`.

### 7.3 LOCK-IN — retiré

Preuve que la liste est toujours vide :

- `activer_lockin` est le seul code qui ajoute une entrée ; `git grep` ne lui trouve aucun appelant,
  et `git log -S"activer_lockin("` ne renvoie que le premier commit du dépôt (sa définition) :
  elle n'a jamais été appelée.
- Les deux autres écrivains (`lister_lockin`, `desactiver_lockin`) n'écrivent qu'un sous-ensemble de
  ce qu'ils ont lu. Parti d'un fichier absent ou vide, le contenu reste `[]`.
- Avec une liste vide, `sorted(positions, key=…)` reçoit la même clé pour toutes les positions ; le
  tri de Python est stable : l'ordre est celui de `lire_positions_ouvertes`. Aucune position n'est
  « en LOCK-IN », `desactiver_lockin` n'est jamais atteinte.
- Le fichier `data/lockin_assets.json` de la tour n'a pas été ouvert (interdit de la session) : la
  preuve repose sur le code et sur l'histoire git.

Parti : `agents/paper_trader/lockin.py` ; dans `monitor.py`, l'import, la lecture de la liste, le
tri, les clés `lockin` et `lockin_actifs` du résultat ; la mention dans la ligne de journal du
moniteur et de `cycle_critical.py`.

Effet de bord, sans lien avec une décision : le moniteur ne réécrit plus `data/lockin_assets.json`
(il y écrivait `[]` à chaque passage). Le fichier reste sur le disque, toujours ignoré par git.

### 7.4 Canal géopolitique de l'intuition — retiré

Preuve que la clé n'est jamais présente : `analyses["context"]` n'est construit qu'à un endroit,
`asset_analyzer.py:116` (`dict(sentiment_global or {})`), puis reçoit `regime_marche`, `regime_adx`,
`regime_global`. `sentiment_global` n'est passé que par `orchestrator.py:113` (4 clés : `fg_valeur`,
`fg_label`, `dominance`, `corr_btc_spy`) et par `scripts/jev_essai.py` (qui n'appelle pas
`decider`). Le tactical, le chat et le conseiller réel n'en passent pas. `actifs_a_surveiller`
n'existe que dans la sortie de `geopolitics.py`, lue par l'analyste de sentiment et l'explorateur de
matières premières, jamais copiée dans le contexte.

Parti : le bloc 4 de `consulter_intuition` et la variable `geo`. `tests/test_intuition_journal.py`
construisait un contexte avec une liste `actifs_a_surveiller` toujours vide : le paramètre est
retiré, les 3 tests sont inchangés.

### 7.5 Docstring de « ajustement » — corrigée

Elle disait « à ajouter au score composite ». Le code ne l'ajoute pas : la valeur (−2 à +2) donne le
pressentiment et, à ±2, l'override. La docstring le dit maintenant ; celle de `boost_confiance`
donne la plage réelle (−1 à +1).

### 7.6 `_seuil_confiance_requis` — retiré

Preuve : `git grep -n "seuil_confiance_requis\|seuil_conf\b"` → la définition, son appel et la clé
du résultat, dans `decision_engine.py` seulement. Aucun lecteur (mêmes consommateurs qu'en 7.1).
`WINRATE_PRUDENCE` reste : `_verifier_overrides` la lit.

### 7.9 Audit métacognitif — NON FAIT

`audit_metacognitif` et `METACOG_AUDIT_ENABLED` sont restés, pour deux raisons :

1. `METACOG_AUDIT_ENABLED` entre dans l'empreinte des paramètres du registre. La retirer de
   `config.py` fait passer sa valeur de `False` à `None` dans l'empreinte ; la retirer aussi de la
   liste change l'empreinte autrement. Dans les deux cas, une écriture du registre change à chaque
   passage, pendant la fenêtre Q3.a.
2. La branche n'est inatteignable que si l'interrupteur est éteint dans le `.env` de la tour, que
   je n'ai pas le droit de lire. S'il était allumé, la fonction ferait un appel LLM (Groq, hors
   réserve Gemini) par décision non-HOLD : la retirer changerait la charge sur Groq, que le pipeline
   utilise aussi pour ajuster la taille des positions.

Ce qui est prouvé : le champ `metacognition` du résultat n'est lu par aucun code
(`decision_formatter.py:133` et `registre_cycles.py:99` lisent le `metacognition` du pipeline, pas
celui-ci). Le retrait demande donc seulement une note de rupture d'empreinte au registre : décision
de Lucia, reportée dans le TODO au lot 7.

### 7.13 `EXCLURE_BOUCLES_STATS`

`grep -c "EXCLURE_BOUCLES_STATS" .env` (copie de production) → `0` : la variable n'est pas dans le
`.env` de la tour. Le défaut du code s'applique (`config.py` : `"0"`) : **elle vaut 0**. Les
statistiques paper comptent donc encore les positions « boucle ». La phrase de `CLAUDE.md` et de
`.env.example` (« à 0 jusqu'au 28/10/2026 ») est corrigée au lot 6.

### Non touchés (consigne)

7.7 arrêt d'urgence, 7.8 veto Fear & Greed du tactical, 7.10 `setups_similaires`, 7.15 risque en
mode défensif, 4.3 `signal_results`, 6.3 `lessons_learned` : les corriger changerait des décisions.
Ils sont listés dans le TODO, section « Lot comportement » (lot 7).

Tests : `Ran 459 tests` / `OK (skipped=10)`.

## Lot 6 — Documentation

Parti :

- Les 10 `CLAUDE.md` restants des sous-dossiers de `agents/` (8.29 ; le onzième,
  `agents/backtester/CLAUDE.md`, est parti au lot 4). Deux docstrings qui renvoyaient à ces fichiers
  (`market_analyst/analyst.py`, `risk_manager/manager.py`) ne les citent plus.
- `docs/BROUILLON_RUPTURE_PRIX_ENTREE.md` et `docs/BROUILLON_CRITERE_EXPLORATEURS.md` (8.35), et la
  référence de `docs/TODO.md` §42 vers le second.

Corrigé dans `CLAUDE.md` (racine) :

- 8.1 : 16 routes `/api/real/*` (17 à l'inventaire, moins `GET /api/real/calibrate/<ticker>`).
- 8.2 : univers de 224 actifs, 207 à 212 par passage.
- 8.3 : la watchlist n'est modifiée que depuis le dashboard.
- 8.4 : convergence non exigée (`CONVERGENCES_REQUISES = 0`).
- 8.5 : une contradiction majeure ne bloque plus, elle réduit la taille (× 0,5) ; les trois vrais
  overrides sont nommés.
- 8.6 : poids du risque présent, contribution toujours 0.
- 8.13 : la liste des titres du rapport suit ce que le code produit (Synthèse exécutive, Pipeline en
  mode Prudent, Registre des décisions ajoutés ; titres exacts des sections).
- 8.15 : section « Planification — 8 tâches du Planificateur Windows » (les 5 cycles, `cleanup`,
  `dashboard`, `surveillance`, les deux scripts d'installation, les journaux `task_<nom>.log`) ;
  plus de LaunchAgent ni de launchd.
- 8.16 : 20 positions sur la tour par le `.env`, 5 par défaut dans le code et dans `.env.example`.
- 8.17 : `trade_journal.md` ne reçoit que les BUY/SELL du cycle quotidien.
- 8.12 : `EXCLURE_BOUCLES_STATS` vaut 0 (lecture du lot 5) ; même correction dans `.env.example` et
  dans le commentaire de `config.py`.
- Mentions retirées : LOCK-IN (8.9), géopolitique dans l'intuition et le rapport (8.7),
  `weekly_reviews` (8.11), ligne CONVICTION du tableau des modes (8.10). 8.18 : la formule
  d'allocation écrite est devenue exacte au lot 5, elle est restée.
- Ligne ajoutée : « `memory/metacognition_log.md` n'est jamais une source de décision. »

Autres documents :

- `README.md` réécrit pour la v5 sous Windows (8.19 à 8.25) : installation PowerShell, 6 clés
  d'API, 8 tâches planifiées, 14 pages, seuils réels (8 / 9 / 4, R:R 1,2, DEFENSIF à 7), journaux
  `task_<nom>.log`, arborescence complète. La liste « Améliorations futures » est gardée, sans le
  Mac ni le backtester visuel.
- `docs/AVANT_ARGENT_REEL.md` (8.30) : condition 9 marquée « codé » avec la date de mise à jour ;
  le constat du 19/10 est gardé en dessous.
- `docs/CONSOMMATION_API.md` (8.32) : cache CoinGecko de 10 min ; collecte de 51 séries
  (5 cryptos × 3 + 18 × 2, recompté dans `data/watchlist.json.exemple`).
- `docs/HORIZONS.md` (8.33) : prix d'entrée paper tranché et codé.
- `docs/TAILSCALE.md` (8.36) : réécrit pour la tour Windows ; HTTPS par Tailscale Serve présenté
  comme le seul accès.
- `dashboard/templates/budget.html` (8.37) : confiance minimale 7 (DEFENSIF) et 3 (AGRESSIF) ; la
  fiche CONVICTION, jamais affichée (le mode n'est jamais renvoyé), est retirée.
- `utils/scheduler_check.py` (8.38) : `surveillance` ajoutée à `TACHES_WINDOWS` ; « 8 tâches »
  dans le module et dans `scripts/check_status.py`. Ce contrôle n'est lancé qu'à la main.
- `agents/intuition.py` : la docstring du module ne cite plus le contexte géopolitique.

Resté :

- 8.31 (`docs/AVANT_ARGENT_REEL.md:32,50`) : **à signaler.** Le document écrit toujours « Q3.a :
  lecture le 03/11/2026 », « en cours ». La date est passée de 20 jours ; rien dans le dépôt ne dit
  si la lecture a eu lieu. Laissé tel quel, comme demandé.
- 8.34 (`docs/DIAG_PRIX_ENTREE.md`) : archive datée, laissée. Sa ligne 192 renvoie à
  `docs/BROUILLON_RUPTURE_PRIX_ENTREE.md`, supprimé dans ce lot : le renvoi est mort. L'inventaire
  disait ce brouillon « cité par aucun fichier » ; c'était inexact.
- Une mention de CONVICTION reste dans `CLAUDE.md` : la phrase qui explique pourquoi l'entrée de
  `PARAMETRES` est gardée (empreinte du registre).
- `scripts/show_access_urls.py` affiche encore des adresses `http://<ip>:8080` qui ne répondent
  plus et un lien de téléchargement pour Mac ; le script est classé GARDER (1.16) et n'était pas
  dans la consigne. `docs/TAILSCALE.md` prévient de ne pas s'y fier ; reporté au TODO (lot 7).
- 8.8, 8.14 et les lignes de `CLAUDE.md` qui dépendent du lot comportement (arrêt d'urgence à
  700 €, « risque ajusté par mode BM », statistiques par actif) : inchangées, elles suivent des
  décisions à prendre.

Tests : `Ran 459 tests` / `OK (skipped=10)`.

## Lot 7 — `docs/TODO.md`

Le fichier passe de 1 044 à 560 lignes. Les numéros des entrées restantes n'ont pas changé : le code
et les autres documents citent « TODO §N » à de nombreux endroits.

Parti (23 entrées) :

- Les 20 entrées classées SUPPRIMER en section 12 : entrée de tête sur les décisions du tactical,
  §1, 6, 9, 10, 13, 16, 18, 19, 23, 28, 30, 34, 35, 36, 37, 38, 39, 40, 41.
- §11 et §24, notes que le registre porte déjà.
- §15 (`_seuil_confiance_requis`) : la fonction a été supprimée au lot 5, l'entrée n'a plus d'objet.
  Ce retrait n'était pas dans la consigne du lot 7 ; il découle du lot 5.
- Une table en fin de fichier, « Entrées sorties le 23/11/2026 », garde une ligne par entrée sortie
  (titre, ce qui l'a close), pour que les renvois « TODO §N » du code restent lisibles.

Reliquats reportés dans une entrée restante :

- « BM en attente » (entrée de tête) → §26.
- `get_real_budget_summary` et `progression_plan` (§35, inventaire 1.32) → §32.
- `EXCLURE_BOUCLES_STATS` toujours à 0 (§40, 7.13) → section de tête.
- `logs/task_*.log` jamais bornés (§1), clés d'API dans l'URL de `check_status.py` et anciens
  journaux à supprimer à la main (§37) → nouvelle entrée §43, « Reliquats du nettoyage ».
- §39 (`ajouter_lecon`) : plus de reliquat, la fonction est partie au lot 1.

Réduit à ce qui reste : §2 (Groq), §7 (`PUT /api/plans/<id>`), §8 (trois cas), §27 (actifs sans
fondamental, pas de cache Alpha Vantage), §31 (`sous_repartition`, `max_position_size`), §42 (EMA 200,
biais d'ordre, prix de la queue).

Références corrigées : les entrées gardées citent des fonctions au lieu de numéros de ligne (têtes,
§12, 14, 20, 21, 22, 25, 26, 29). §20 : la docstring fausse est dite corrigée, le pilier
géopolitique retiré. §27 : la coupure d'Alpha Vantage est dans `scripts/_chat_a_blanc.py`. Entrée
`signal_results` : la démo est dans `agents/trade_journalist/demo_performance.py`. §32 : n'annonce
plus de tailles de fichiers périmées.

Ajouté :

- En tête, « Lot comportement — après la lecture Q3.a » : arrêt d'urgence (7.7), veto Fear & Greed
  au tactical (7.8), risque en mode défensif (7.15), `setups_similaires` (7.10), alimentation de
  `signal_results` (4.3). Chacun exige un critère commité au registre avant d'être codé.
- §43 : ce que le nettoyage laisse (audit métacognitif et entrée CONVICTION liés à l'empreinte du
  registre, trailing stop sans commande, `jev_essai.py` non classé, `show_access_urls.py`, colonne
  `devise` sur une base neuve, fichiers d'état devenus inutiles).

Resté tel quel : §3, 4, 17, 33 ; §5 reçoit une ligne qui renvoie à `CLAUDE.md`.

À savoir : les identifiants de commit cités dans le TODO et dans `docs/` sont ceux de l'historique
d'avant la réécriture du dépôt public ; ils n'existent pas dans l'historique actuel. Non corrigé
(hors consigne), signalé au §43.

Tests : `Ran 459 tests` / `OK (skipped=10)` (aucun code touché dans ce lot).
