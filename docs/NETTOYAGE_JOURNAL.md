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
