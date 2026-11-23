# Inventaire avant nettoyage — TradingX / AlphaSignal

- Date : 23/11/2026. Branche `nettoyage`, créée depuis `main` au commit `c76f6a3`.
- Session d'inventaire seulement : aucun fichier existant n'a été modifié ni supprimé. Ce rapport est
  le seul fichier ajouté.
- Chaque ligne porte sa preuve : la commande lancée et son résultat. Sauf mention contraire, les
  commandes sont lancées à la racine du dépôt, au commit `c76f6a3`.
- Classement : **SUPPRIMER** (avec le risque), **GARDER**, **À DÉCIDER** (avec la question).

## 0. Référence d'avant nettoyage : la suite de tests

Commande : `.venv\Scripts\python.exe -m unittest discover -s tests` (Python 3.12.10), lancée dans un
worktree neuf de la branche, réseau coupé par `HTTP_PROXY=HTTPS_PROXY=ALL_PROXY=http://127.0.0.1:9`.

| Lancement | Tests | Passés | Échoués | Erreurs | Ignorés |
|---|---|---|---|---|---|
| Worktree neuf (sans `graphify-out/graph.json`, fichier hors git) | 470 | 460 | 0 | 0 | 10 |
| Même worktree, avec une copie de `graphify-out/graph.json` | 470 | 470 | 0 | 0 | 0 |

- Résultat brut : `Ran 470 tests in 25.924s` / `OK (skipped=10)` ; second lancement identique
  (`Ran 470 tests in 24.129s`, `OK (skipped=10)`). Avec le graphe : `Ran 470 tests in 30.258s` / `OK`.
- Les 10 tests ignorés sont tous dans `tests/test_topology.py` (`TestCarteDuDepot` : 7,
  `TestRoute` : 3), motif « graphify-out/graph.json absent ».
- Aucune ligne `proxy`, `HTTP Error` ou `Failed to` dans la sortie : aucun appel réseau tenté.
- La suite n'a pas été lancée dans la copie de production (elle y côtoierait `data/`).

### Constat préalable : `origin/main` ne correspond plus au `main` local

- `git fetch origin` puis `git rev-list --left-right --count main...origin/main` → `161	88` ;
  `git merge-base main origin/main` → aucun ancêtre commun.
- `origin/main` = `562ae4a` (88 commits, dernier daté du 08/10/2026). `main` local = `c76f6a3`
  (161 commits, dernier daté du 21/10/2026).
- Journal public du dépôt (`api.github.com/repos/<dépôt>/activity`) : deux `force_push` sur
  `refs/heads/main` le 23/10/2026 (08:19 et 09:12 UTC), `efb4003 → 387d569 → 562ae4a`. Aucun ne vient
  de ce clone (`git reflog origin/main` : dernier envoi local = `efb4003`, le 21/10).
- Les 86 premiers commits ont les mêmes arbres des deux côtés (comparaison des `%T` un à un) ; les
  identifiants diffèrent parce que les messages diffèrent : aucun message distant ne porte de ligne
  `Co-Authored-By` (0 sur 88), contre 156 sur 161 en local
  (`git log <réf> --format=%B | grep -c -i "^Co-Authored-By"`). Le distant a en plus 2 commits
  absents ici (`48bfcd3`, `scripts/jev_essai.py`, et `562ae4a`).
- Conséquence : pousser `nettoyage` republierait sur le dépôt public les 161 commits locaux que la
  réécriture du 23/10 a retirés. **La branche n'a donc pas été poussée** ; voir la question Q1.

### Méthode et limites

- Graphe d'imports par analyse AST des 298 fichiers `.py` suivis (imports dans les fonctions compris),
  complété par les 4 sites d'import dynamique (`git grep -n -E "import_module\(|__import__\("`) :
  `agents/rapport_annexes.py:29`, `scripts/cycle_daily.py:45`, `utils/bloc_borne.py:52`,
  `scripts/cycle_tactical.py:43`.
- Points d'entrée de production = les 8 tâches de `\AlphaSignal\`
  (`Get-ScheduledTask -TaskPath '\AlphaSignal\'`) : `cleanup`, `critical`, `daily`, `dashboard`,
  `strategic`, `surveillance`, `tactical`, `weekly`.
- Une fonction « jamais référencée » = son nom n'apparaît nulle part ailleurs que sur sa ligne `def`
  (`git grep -w -n <nom> -- '*.py' '*.html' '*.js' '*.ps1' '*.sh'` → 1 occurrence). Un appel par nom
  construit à l'exécution échapperait à ce contrôle ; aucun des 4 sites dynamiques ne le fait.
- Tables SQLite : analyse du SQL écrit dans le code. **Les bases de `data/` n'ont pas été ouvertes**
  (interdit de la session) : une table présente en base mais absente du code ne serait pas vue, et
  aucun nombre de lignes n'est donné.
- Jev : seul le code est listé ; aucun résultat du portefeuille fantôme n'a été lu ni calculé.
- `.env` non lu : l'état des interrupteurs (`EXCLURE_BOUCLES_STATS`, `JEV_OBSERVE`…) est inconnu.

## 1. Modules et fonctions Python jamais importés ni appelés

### 1.a Modules hors de portée des 8 tâches planifiées

Résultat du parcours : 298 modules, 204 atteints depuis les 8 tâches (167 par import statique,
37 par import dynamique), 67 fichiers de `tests/`, 27 modules de code non atteints, ci-dessous.

| # | Module (lignes) | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 1.1 | `main.py` (37) | Importé par aucun fichier ; lancé par aucune tâche. Corps : `# TODO Phase 3.2+ : initialiser les sous-agents et lancer le scheduler` (l.32). | **SUPPRIMER** | Moyen. Déclaré point d'entrée à 3 endroits : `scripts/graphify_modules.py:23`, `dashboard/api/etat_code.py:63`, `dashboard/api/topology_composants.py:80` ; cité `README.md:216`, `docs/AVANT_ARGENT_REEL.md:128`. La page Architecture et `tests/test_topology.py` (classement de tous les modules) sont à ajuster. |
| 1.2 | `scripts/check_health.py` (175) | `diff scripts/check_health.py scripts/check_status.py` → 0 ligne différente : copie exacte. | **SUPPRIMER** | Faible. Cité par `README.md` et `docs/TODO.md` §34 ; garder `check_status.py`, que citent `scripts/cycle_daily.py:66` et `scripts/run_mac.sh`. |
| 1.3 | `scripts/check_status.py` (175), `utils/scheduler_check.py` (91) | Lancés à la main. `scheduler_check` n'a que ces deux importeurs. | **GARDER** | — (`TACHES_WINDOWS`, `utils/scheduler_check.py:15`, liste 7 tâches : `surveillance` manque, voir §8.) |
| 1.4 | `scripts/check_after_update.py` (249) | « Vérifs post-mise-à-jour macOS » (l.3) : `launchctl` (l.123), `pmset` (l.176, 193), miniconda (l.52). Cité seulement par `scripts/backup_before_update.sh`. | **À DÉCIDER** | Le Mac est-il encore une machine cible, ou la tour Windows est-elle la seule ? (même question que 5.2) |
| 1.5 | `scripts/check_message_audit.py` (111) | Cité par aucun fichier (`git grep -l check_message_audit` → lui seul), aucun test. | **À DÉCIDER** | Te sers-tu encore de cette vérification manuelle de l'audit du chat, maintenant que la page Audit existe ? |
| 1.6 | `scripts/reparer_barres_incompletes.py` (182) | Réparation ponctuelle (P10). Cité par aucun fichier, aucun test. | **À DÉCIDER** | Les barres figées d'avant P10 sont-elles toutes réparées, ce qui rend le script inutile ? |
| 1.7 | `scripts/reparer_prix_null.py` (148) | Réparation ponctuelle. Cité par aucun fichier, aucun test. | **À DÉCIDER** | Veux-tu le garder au cas où des prix NULL reviendraient ? |
| 1.8 | `scripts/purger_signaux_demo.py` (200) | Purge ponctuelle (SIG-0001 à 0005), dite appliquée le 08/10 dans `docs/TODO.md` (tête B). 4 tests (`tests/test_purger_signaux_demo.py`). | **À DÉCIDER** | La purge étant appliquée, peut-on retirer le script et ses 4 tests ? |
| 1.9 | `scripts/migrer_devise_reelle.py` (115) | Migration D1 ; 7 tests (`test_real_devise_migration.py`). Non citée dans la documentation. | **À DÉCIDER** | La migration de devise du portefeuille réel a-t-elle été lancée sur la tour ? Si oui, le script peut partir. |
| 1.10 | `scripts/seed_plans.py` (153) | Amorçage ponctuel des plans ; cité par `docs/HORIZONS.md`, `docs/TODO.md` ; lu par `tests/test_plan_repartition.py`. | **À DÉCIDER** | Les plans sont-ils créés pour de bon, ce qui rend l'amorçage inutile ? |
| 1.11 | `scripts/marquer_boucles.py` (125) | Cité par `CLAUDE.md`, `.env.example`, le registre ; relançable. | **GARDER** | — |
| 1.12 | `scripts/q3a_compteur.py` (129) | Cité par `docs/AVANT_ARGENT_REEL.md` ; 7 tests. | **GARDER** | — |
| 1.13 | `scripts/run_analysis.py` (48), `scripts/daily_routine.py` (115) | Lancements manuels de la routine ; 4 et 3 tests. | **GARDER** | — |
| 1.14 | `scripts/rapport_verif_chiffres.py` (144) | Outil manuel du contrôle des chiffres du chat ; `tests/test_verif_chiffres.py` (34 tests). | **GARDER** | — |
| 1.15 | Banc de rejeu du chat : `scripts/_banc_fichiers.py` (107), `_banc_rejeu.py` (174), `_chat_a_blanc.py` (178), `chat_cas_export.py` (118), `rejouer_chat.py` (164), `agents/chat/_banc_notation.py` (112), `agents/chat/_banc_resume.py` (159) | Outil manuel, 7 modules de test (`test_banc_*`, `test_chat_a_blanc*`). `_banc_fichiers` est importé par `tests/journaux_isoles.py`, donc par toute la suite. | **GARDER** | — |
| 1.16 | Tailscale : `scripts/setup_tailscale.py` (73), `teardown_tailscale.py` (35), `show_access_urls.py` (123), `utils/tailscale.py` (57) | Cités par `docs/TAILSCALE.md`, `README.md`, `.env.example`. | **GARDER** | — |

### 1.b Modules atteints seulement par une route sans consommateur (voir §2)

| # | Module (lignes) | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 1.17 | `agents/technical_skills/performance_attribution.py` (114), `backtester_pro.py` (139), `scenario_simulation.py` (142), `news_catalyst.py` (105), `economic_calendar.py` (132), `correlation.py` (127) | `git grep -n -E "technical_skills\|backtester" -- '*.py'` : seul importeur de chacun = `dashboard/api/routes.py` (l.148, 156, 164, 177, 197, 211), dans une route sans consommateur. | **À DÉCIDER** | Voir 2.1 : ces six analyses (attribution, backtest, stress-test, catalyseurs, calendrier, corrélation) doivent-elles avoir une page, ou partir ? |
| 1.18 | `agents/backtester/engine.py` (214), `agents/backtester/metrics.py` (112), `agents/backtester/CLAUDE.md` | Seul importeur : `agents/technical_skills/backtester_pro.py:19,24`. `metrics` est aussi appelé par `tests/test_sources_passage.py:79`. | **À DÉCIDER** | Suit la réponse à 2.1 (route `/api/backtest/<ticker>`). |

### 1.c Fonctions jamais référencées

Preuve commune : `git grep -w -n <nom> -- '*.py' '*.html' '*.js' '*.ps1' '*.sh'` → 1 occurrence, la
ligne `def` indiquée.

| # | Fonction | Classement | Risque / question |
|---|---|---|---|
| 1.19 | `agents/analysts/fundamental_analyst/macro.py:91` `recuperer_prix_dernier` | **SUPPRIMER** | Faible. |
| 1.20 | `agents/budget_manager/manager.py:118` `formater_section_budget` | **SUPPRIMER** | Faible. |
| 1.21 | `agents/knowledge/pretrade_analysis.py:160` `formater_markdown` | **SUPPRIMER** | Faible : le mode « complet » de l'analyse pré-trade n'est affiché nulle part ; `CLAUDE.md` l'annonce (« mode complet/condensé »). |
| 1.22 | `agents/orchestrator.py:42` `_signal_depuis_analyses` | **SUPPRIMER** | Faible ; allège un fichier de 276 lignes. |
| 1.23 | `agents/skills/_json_helper.py:43` `reponse_vide` | **SUPPRIMER** | Faible. |
| 1.24 | `agents/trade_journalist/journalist.py:150` `lister_signaux_recents` | **SUPPRIMER** | Faible. |
| 1.25 | `agents/trade_journalist/performance_tracker.py:183` `ajouter_lecon` | **SUPPRIMER** | Faible ; emporte la constante `LESSONS_LEARNED_FILE` (l.19), que `demo_performance.py:47` redirige. |
| 1.26 | `scripts/fetch_data.py:95` `recuperer_prix_coingecko` | **SUPPRIMER** | Faible. |
| 1.27 | `utils/data_fetcher.py:108` `info_actif`, `:116` `recuperer_lot` | **SUPPRIMER** | Faible. |
| 1.28 | `utils/database.py:181` `lire_prix` | **SUPPRIMER** | Faible. |
| 1.29 | `utils/gemini.py:239` `stats_usage` | **SUPPRIMER** | Faible ; allège un fichier de 249 lignes. |
| 1.30 | `utils/lock_manager.py:134` `cycles_actifs` | **SUPPRIMER** | Faible. |
| 1.31 | `utils/real_price.py:216` `prix_actuel_calibre`, `:229` `get_display_entry_price` | **SUPPRIMER** | Faible à moyen : module des prix du portefeuille réel (285 lignes) ; relancer les tests `test_real_*`. |
| 1.32 | `utils/real_portfolio_db.py:196` `get_real_budget_summary`, `:626` `progression_plan` | **SUPPRIMER** | **Élevé.** Aucun appelant hors tests (`git grep -w` : la définition, deux docstrings de `utils/real_vue.py:33` et `utils/real_conversion.py:87,124`). Mais 4 modules de test s'en servent comme calcul de référence du portefeuille réel (`test_real_conversion.py:71,106,138`, `test_real_sans_prix.py:67,74`, `test_real_devise.py:155`, `test_plan_sans_position.py:82`) : ces tests sont à réécrire d'abord, sinon la comparaison disparaît avec la fonction. |
| 1.33 | `agents/paper_trader/lockin.py:60` `activer_lockin`, `:80` `est_en_lockin` | **À DÉCIDER** | Voir 7.3 (LOCK-IN jamais activé). |
| 1.34 | `agents/technical_skills/correlation.py:100` `evaluation_nouvelle_position`, `economic_calendar.py:121` `alerte_evenement_proche`, `scenario_simulation.py:26` `simuler_trade` | **À DÉCIDER** | Dans des modules de 1.17 ; suit la réponse à 2.1. |
| 1.35 | `agents/chat/_banc_notation.py:52` `est_note` | **GARDER** | Référencée par les tests seulement (`tests/test_banc_notation.py:19,79`) ; outil du banc (1.15). |

Faux positif écarté : `utils/journal_rotation.py:38` `RotationTolerante.doRollover` et
`utils/secret_mask.py:80` `FiltreSecrets.filter` sont appelées par le module `logging`.

## 2. Routes Flask sans aucun consommateur

81 routes relevées (décorateurs `@….route` de `dashboard/`). Pour chacune, recherche du chemin dans
`dashboard/templates/`, `dashboard/static/`, `scripts/`, `utils/`, `agents/`, `alerts/`. 68 ont au
moins un consommateur ; 13 n'en ont aucun (`grep -rn -F "<chemin>" dashboard/templates
dashboard/static scripts utils agents alerts` → rien, ou seulement une constante de
`utils/registre_manuel.py` et une ligne de documentation).

| # | Route (`dashboard/api/routes.py`) | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 2.1 | `GET /api/attribution` (l.146), `/api/backtest/<ticker>` (l.154), `/api/stress-test` (l.161), `/api/news-catalysts` (l.175), `/api/calendar` (l.195), `/api/correlation` (l.209) | Aucun `fetch` dans les 15 gabarits ni les 4 scripts JS. `/api/correlation` n'est cité que par `agents/technical_skills/CLAUDE.md:32`. | **À DÉCIDER** | Ces six analyses n'ont aucune page : veux-tu les afficher quelque part, les garder comme adresses à ouvrir à la main, ou les supprimer avec leurs modules (1.17, 1.18, environ 1 085 lignes) ? |
| 2.2 | `GET /api/regime` (l.216), `GET /api/liquidity/<ticker>` (l.188) | Aucun consommateur. Leurs modules (`market_regime`, `liquidity`) servent ailleurs (`agents/asset_analyzer.py:122`, `scripts/cycle_strategic.py:57`, `setup_quality.py:87`). | **À DÉCIDER** | Même question que 2.1 ; seule la route partirait, pas le module. |
| 2.3 | `GET /api/intuition` (l.122) | Aucun consommateur. `stats_intuition`, qu'elle appelle, sert déjà au chat (`agents/chat/context_builder.py:123`) et au rapport hebdo (`scripts/cycle_weekly.py:54`). | **À DÉCIDER** | Veux-tu voir les statistiques d'intuition sur la page Memory, ou retirer la route (la fonction reste) ? |
| 2.4 | `POST /api/positions/<id>/trailing-stop` (l.129) | Aucun bouton ni `fetch` ; seule mention : `utils/registre_manuel.py:24` (libellé de registre). Seule route qui écrit une position paper à la main. | **À DÉCIDER** | Te sers-tu de cette route à la main (curl) pour poser un trailing stop ? Sinon elle part, avec `noter_trailing`. |
| 2.5 | `GET /api/positions/<id>` (l.40) | Aucun consommateur (`portfolio.html` appelle `/api/positions`, sans identifiant). | **SUPPRIMER** | Faible. `queries.position_detail` n'aurait plus d'appelant. |
| 2.6 | `POST /api/settings/watchlist` (l.565) | Remplacée par `POST /api/settings/watchlist/actif` (`settings.html:134`, P14). Seule mention : `utils/registre_manuel.py:25`. | **SUPPRIMER** | **Moyen.** Elle réécrit tout `data/watchlist.json` : une ancienne page Settings gardée en cache par le service worker de l'iPhone pourrait encore l'appeler. Vérifier la version du cache (`dashboard/static/sw.js`) avant de la retirer ; `ROUTE_WATCHLIST` reste la valeur par défaut de `noter_watchlist` (`registre_manuel.py:65`). |
| 2.7 | `GET /api/real/calibrate/<ticker>` (l.485) | Aucun consommateur (`real.html:498` appelle le `POST /api/real/calibrate`, sans ticker). | **SUPPRIMER** | Faible. |

## 3. Templates et fichiers statiques non référencés

Aucun. 15 gabarits : chacun est rendu par une route (`render_template` dans `dashboard/app.py` ou
`dashboard/api/jev_fantome_routes.py`), `base.html` est étendu par les 14 autres. 9 fichiers
statiques : `app.css`, `sw.js`, `manifest.json` et `icon-192.png` sont cités par `base.html`,
`icon-512.png` par `manifest.json`, les 4 scripts JS par `architecture.html` ou `audit.html`.

| # | Élément | Preuve | Classement |
|---|---|---|---|
| 3.1 | 15 gabarits, 9 fichiers statiques | Recherche du nom de chaque fichier dans tous les fichiers suivis : au moins une référence pour chacun. | **GARDER** |

## 4. Tables SQLite jamais lues, ou jamais écrites

24 tables créées par le code (`git grep -n -i "CREATE TABLE"`). Bases non ouvertes (voir Méthode).

| # | Table | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 4.1 | `indicators` | Créée `utils/database.py:54`. Aucun `SELECT`, `INSERT`, `UPDATE` ni `DELETE` dans le code ; seule autre mention : `utils/audit_trace.py:26` (`TABLES_CACHE`). | **SUPPRIMER** (le `CREATE TABLE`) | Faible. La table existante reste dans `database.db` (rien n'y touche) ; retirer `"indicators"` de `TABLES_CACHE`. |
| 4.2 | `sentiment` | Créée `utils/database.py:113`. Jamais lue ni écrite (`git grep -n -i -E "(FROM\|INTO\|UPDATE)[^\"']{0,30}\bsentiment\b"` → le `CREATE` seul) ; citée dans `TABLES_CACHE`. | **SUPPRIMER** (le `CREATE TABLE`) | Faible, comme 4.1. |
| 4.3 | `signal_results` | Lue par 5 modules (`journalist.py`, `performance_tracker.py`, `dashboard/api/queries.py`, `utils/memory_lookups.py`, `purger_signaux_demo.py`). Écrite par le seul `journalist.py:137` (`cloturer_signal`), dont le seul appelant est la démo (`demo_performance.py:71`) : jamais écrite par un cycle. | **À DÉCIDER** | `docs/TODO.md` (tête B) est toujours vrai : veux-tu alimenter cette table à la fermeture des positions, ou retirer les lecteurs qui en dépendent (winrate, statistiques) ? |
| 4.4 | `rotation_hypothetique` | Écrite `agents/rotation_fantome.py:72` ; lue par aucun code (un test seulement). | **GARDER** | Observation voulue de la rotation v5 (`CLAUDE.md`, registre) ; sa lecture viendra avec le critère. |
| 4.5 | `market_regime` | Lue et écrite par `agents/technical_skills/market_regime.py`, mais créée dans `utils/real_portfolio_db.py` (schéma du portefeuille réel). | **GARDER** | Rangement seulement : le `CREATE` n'est pas au bon endroit. |
| 4.6 | Les 19 autres tables | Chacune a au moins un lecteur et un écrivain dans le code de production. | **GARDER** | — |

## 5. Scripts qu'aucune tâche planifiée ni aucun autre code ne lance

Tâches réelles (`Get-ScheduledTask -TaskPath '\AlphaSignal\'`) : `critical` (5 min), `tactical`
(15 min), `strategic` (4 h), `daily` (deux déclencheurs quotidiens), `weekly` (hebdomadaire),
`cleanup` (hebdomadaire), `dashboard` (au démarrage), `surveillance` (5 min). Elles lancent
`scripts/cycle_*.py`, `scripts/cleanup.py`, `scripts/surveiller_dashboard.py`, `dashboard/app.py`.
Lancés par un autre code : `sync_vault_trading.py` (`cycle_daily.py:40`), `regenerer_graphe.py`
(`cycle_weekly.py:25`) puis `sync_graphify_vault.py` et `graphify_modules.py` ; importés comme
bibliothèques : `fetch_data.py`, `jev_bilan.py`, `jev_bilan_calc.py`, `verifier_registre.py`.

| # | Script | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 5.1 | Les 22 fichiers Python de `scripts/` hors de portée des tâches (19 scripts lancés à la main, 3 modules d'appui préfixés `_`) | Ce sont les lignes 1.2 à 1.16 ; classés là. | (voir §1) | — |
| 5.2 | `scripts/com.alphasignal.*.plist` (7 fichiers), `install_launchd.sh`, `uninstall_launchd.sh`, `install_v4.sh`, `run_mac.sh`, `backup_before_update.sh` | Mécanisme launchd (macOS). Les tâches en service sont celles du Planificateur Windows ; aucune tâche ni aucun code Python ne lance ces fichiers (`run_mac.sh` n'est cité que par les `.plist`, `install_v4.sh` et le README). | **À DÉCIDER** | Le Mac est-il encore une machine cible ? Si non, ces 12 fichiers et `check_after_update.py` (1.4) partent, et `CLAUDE.md`/`README.md` sont à réécrire pour Windows. |
| 5.3 | `scripts/install_tasks_windows.ps1`, `scripts/installer_surveillance.ps1` | Créent les 7 + 1 tâches en service. | **GARDER** | — |
| 5.4 | `scripts/jev_bilan.py` (lancement en script) | Lecture unique prévue le 11/01/2027 (registre §7) ; non lancé d'ici là. | **GARDER** | — |

## 6. Fichiers de `memory/` et de `agents/knowledge/` qu'aucune décision ne lit

| # | Fichier | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 6.1 | `memory/performance_tracker.md` | Lu par `agents/memory_reader.py:36` → `asset_analyzer.py:118` → intuition (`intuition.py:54`) et winrate du Budget Manager (`paper_trader/cycle.py:52`). | **GARDER** | Lu par une décision. Sa table par actif vient de `signal_results` (voir 4.3). |
| 6.2 | `memory/market_patterns.md` | Lu par `memory_reader.py:71` → `intuition.py:73-76` (ajustement +1). | **GARDER** | Lu par une décision. |
| 6.3 | `memory/lessons_learned.md` | Lu par `memory_reader.py:54`, mais `intuition.py:79-81` n'en tire qu'une phrase de « raisons » : aucun ajustement, aucun effet sur la décision. | **À DÉCIDER** | Les leçons doivent-elles peser sur la décision, ou rester un texte affiché ? |
| 6.4 | `memory/trade_journal.md` | Écrit par `journalist.py:74` ; lu seulement par la page Memory (`routes.py:81`). | **GARDER** | Journal (« jamais supprimer ») ; aucune décision ne le lit. |
| 6.5 | `memory/intuition_log.md` | Écrit par `intuition.py:170` ; relu par `intuition_tracker.py` (résultats) et le vault. `decision_engine.py:190` : « journal seulement : rien n'est lu en retour ». | **GARDER** | Journal ; aucune décision ne le lit. |
| 6.6 | `memory/metacognition_log.md` | Un seul accès, en écriture : `agents/skills/_log.py:17,59` (`git grep metacognition_log -- '*.py'`). Lu par aucun code. | **À DÉCIDER** | L'audit métacognitif étant éteint par défaut (7.9), garde-t-on ce fichier et son écrivain ? |
| 6.7 | `memory/weekly_reviews/` | Annoncé `CLAUDE.md:136`. `git grep weekly_reviews -- '*.py'` → 0 ; le dossier n'existe pas sur la tour. | **SUPPRIMER** (la ligne de `CLAUDE.md`) | Aucun. |
| 6.8 | `memory/*.md.exemple` (4 fichiers) | Copiés par `utils/memoire_modeles.py` quand le fichier manque. | **GARDER** | — |
| 6.9 | `agents/knowledge/knowledge_base.py` | Importé par `agents/chat/context_builder.py:129` (chat) et `pretrade_analysis.py:16`. Aucune décision. | **GARDER** | Sert au chat et à l'affichage. |
| 6.10 | `agents/knowledge/chart_reading.py`, `pretrade_analysis.py` | Importés par `agents/rapport_pretrade.py:14-15`, section d'affichage du rapport (`rapport_annexes.py:22`). Aucune décision. | **GARDER** | Affichage seulement, comme le dit `CLAUDE.md`. |
| 6.11 | `agents/knowledge/CLAUDE.md` | Documentation du dossier. | **GARDER** | À relire avec §8. |

## 7. Fonctions câblées à moitié

| # | Élément | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 7.1 | `budget_boost` | Produit `agents/decision_engine.py:199,203` et `setup_quality.py:112` ; lu `agents/budget_manager/arbitrator.py:27` (`demande.get("budget_boost", 1.0)`). Mais `creer_demande` (`manager.py:22-38`) et son seul appel (`paper_trader/cycle.py:45-53`) ne copient jamais la clé : le facteur vaut toujours 1.0. | **À DÉCIDER** | Le grade du setup doit-il moduler l'allocation (un changement de comportement, donc un critère au registre), ou retire-t-on la lecture ? |
| 7.2 | Mode CONVICTION | `conviction_force` existe sur `traiter_demandes` (`manager.py:51`) et `detecter_mode` (`strategy.py:86`), mais le seul appel est `traiter_demandes(demandes)` (`paper_trader/cycle.py:71`) ; aucune route ni page ne le pose. Le mode est inatteignable. | **À DÉCIDER** | Veux-tu un bouton « conviction » sur le dashboard, ou retirer le mode (et la ligne du tableau de `CLAUDE.md`) ? |
| 7.3 | Mode LOCK-IN | `activer_lockin` et `est_en_lockin` ne sont appelées nulle part (1.33). Le moniteur lit la liste (`monitor.py:91`) et la vide (`monitor.py:118`), mais rien ne la remplit. | **À DÉCIDER** | Qui doit activer le LOCK-IN sur un breakout ? Sans réponse, `lockin.py` et sa mention dans `CLAUDE.md` partent. |
| 7.4 | Intuition, canal géopolitique | `intuition.py:85-86` lit `analyses["context"]["actifs_a_surveiller"]`. Le contexte ne contient que `fg_valeur`, `fg_label`, `dominance`, `corr_btc_spy` (`orchestrator.py:113-118`) et le régime (`asset_analyzer.py:124-129`) ; le tactical n'en passe aucun (`cycle_tactical.py:67`). La clé n'y est jamais : le canal ne se déclenche pas. | **À DÉCIDER** | Faut-il brancher la veille géopolitique sur l'intuition (changement de décision), ou retirer ce canal ? |
| 7.5 | Intuition, champ `ajustement` | La docstring dit « à ajouter au score composite » (`intuition.py:47`) ; `decision_engine.py:161-171` n'utilise que `override_decision` et `boost_confiance`. | **À DÉCIDER** | Corrige-t-on la docstring, ou le score ? (lié à `docs/TODO.md` §20) |
| 7.6 | `_seuil_confiance_requis` | Calculé `decision_engine.py:124`, renvoyé l.187 ; aucun lecteur (`git grep seuil_confiance_requis` → ces lignes seules). `docs/TODO.md` §15. | **À DÉCIDER** | L'appliquer ou le supprimer ? |
| 7.7 | Seuil d'arrêt d'urgence (700 €) | Les 4 contrôles comparent `config.CAPITAL`, une constante lue du `.env`, au seuil (`risk_manager/manager.py:34`, `orchestrator.py:213`, `main.py:23`, `config.py:192`) : le P&L n'entre jamais dans `CAPITAL`, l'arrêt ne peut pas se déclencher. Déjà noté `docs/AVANT_ARGENT_REEL.md:128`. | **À DÉCIDER** | L'arrêt d'urgence doit-il suivre la valeur réelle du portefeuille paper ? |
| 7.8 | Veto Fear & Greed dans le tactical | `decision_engine.py:89-96` lit le contexte ; `cycle_tactical.py:67,98` appelle `analyser_actif_complet` sans `sentiment_global`. `docs/TODO.md` §21. | **À DÉCIDER** | Passer le sentiment global au tactical ? |
| 7.9 | Audit métacognitif des cycles | `METACOG_AUDIT_ENABLED` vaut `false` par défaut (`config.py:77`) ; commentaire l.75 : « résultat lu par aucun code ». | **À DÉCIDER** | Supprimer `audit_metacognitif` et son journal (6.6), ou le garder éteint ? |
| 7.10 | `setups_similaires` | Reçoit BUY ou SELL (`agents/skills/pipeline_grouped.py:75,80`), compare à une colonne qui contient LONG ou SHORT (`utils/memory_lookups.py:114`, `orchestrator.py:228`) : ne trouve jamais rien. `docs/TODO.md` §25. | **À DÉCIDER** | Corriger la comparaison, ou retirer le taux de base du pipeline ? |
| 7.11 | Catalyseurs de l'analyse pré-trade | `CATALYSEURS = "non disponible"` (`pretrade_analysis.py:19`) : section 3 jamais écrite ; mode complet jamais affiché (1.21). | **GARDER** | Assumé et écrit dans `CLAUDE.md`. |
| 7.12 | Rotation v5 | `agents/paper_trader/rotation.py` n'est importé que par `rotation_fantome.py` ; `ROTATION_ACTIVE=1` est refusé (`config.py:153`). | **GARDER** | En observation par choix (registre). |
| 7.13 | Interrupteur `EXCLURE_BOUCLES_STATS` | Défaut 0 (`config.py:146`) ; `CLAUDE.md` : « à 0 jusqu'au 28/10/2026 ». La date est passée ; `.env` non lu. | **À DÉCIDER** | L'interrupteur a-t-il été passé à 1 le 28/10 ? Sinon la phrase de `CLAUDE.md` est périmée. |
| 7.14 | Sortie du mode défensif « après 5 trades » | `NB_TRADES_DEFENSIF_RESET = 5` (`agents/paper_trader/portfolio.py:21`) n'est lue nulle part (`git grep -w` → sa définition seule) ; le mode se lève dès que les 3 dernières positions fermées ne sont plus toutes perdantes (`portfolio.py:40-45`). | **À DÉCIDER** | Supprimer la constante, ou appliquer la règle des 5 trades ? |
| 7.15 | Risque réduit en mode défensif | `risque_par_trade_pct()` (`portfolio.py:48`) n'est lue que pour l'affichage (`paper_trader/cycle.py:156`) ; le dimensionnement utilise `config.RISK_PER_TRADE_PCT` (`risk_manager/manager.py:115`). | **À DÉCIDER** | Le risque par trade doit-il vraiment baisser en mode défensif ? |

## 8. Documentation fausse ou périmée

Les chiffres sont cités tels qu'ils sont écrits, puis tels qu'ils sont dans le code.
`docs/REGISTRE_CRITERES.md` n'a pas été contrôlé (registre daté, figé). Ici **GARDER** veut dire : le
document reste, la ligne est à corriger.

### 8.a `CLAUDE.md` (racine)

| # | Ligne | Écrit | Réel | Preuve | Classement |
|---|---|---|---|---|---|
| 8.1 | 197 | « 7 endpoints `/api/real/*` » | 17 routes (14 chemins) | `grep -c -E '@api\.route\("/real/' dashboard/api/routes.py` → 17 | **GARDER** (corriger) |
| 8.2 | 58 (et `README.md:68`) | « scan ~180 actifs/run » | Univers de 224, soit 207 à 212 par passage hors watchlist | Tailles des univers : actions 50, ETF 47, indices 20, forex 20, matières premières 19, CFD 18, crypto 50 (`crypto_explorer/explorer.py:24`) ; `docs/CONSOMMATION_API.md:34` écrit 207 | **GARDER** (corriger) |
| 8.3 | 33 | Watchlist « élargie automatiquement par les 7 explorateurs » | Seul le dashboard écrit la watchlist | `git grep -n -w ecrire_watchlist` → `dashboard/api/routes.py:577,579`, `watchlist_io.py:94,120` ; les explorateurs n'écrivent que la queue | **GARDER** (corriger) |
| 8.4 | 112 | « Au moins 1 paire de sous-agents convergente » | 0 : non exigé | `agents/paper_trader/rules.py:17` : `CONVERGENCES_REQUISES = 0` (« avant 1 ») | **GARDER** (corriger) |
| 8.5 | 83 | Override « contradiction majeure » | Une contradiction ne bloque plus : taille réduite | `agents/decision_engine.py:128,153-156` | **GARDER** (corriger) |
| 8.6 | 87 | Pondérations « Risk 20 % » | Poids présent, contribution toujours 0 | `agents/asset_analyzer.py:102` : `r["confiance"] = 0  # le risque ne contribue pas en score` | **GARDER** (corriger) |
| 8.7 | 84, 41, 157 | Intuition « géopolitique alignée » ; rapport « incluant géopolitique » | Canal jamais alimenté (7.4) ; la section du rapport ne contient que F&G, dominance, corrélation | `agents/orchestrator.py:113-118` ; `intuition.py:85` | **À DÉCIDER** (suit 7.4) |
| 8.8 | 84, 132, 167 | « winrate ≥ 70 % », stats par actif « auto-MAJ », alerte « Dégradation perf » | Seuils exacts, mais la source `signal_results` n'est écrite par aucun cycle (4.3) | `performance_tracker.py:28-33,74-82` (jointure sur `signal_results`) | **À DÉCIDER** (suit 4.3) |
| 8.9 | 125, 46 | « Mode LOCK-IN : surveillance 5 min… (4h max) » | Constantes exactes (4 h, 300 s), rien ne l'active | Voir 7.3 | **À DÉCIDER** (suit 7.3) |
| 8.10 | 97 | Mode CONVICTION « manuel (1 trade) » | Inatteignable | Voir 7.2 | **À DÉCIDER** (suit 7.2) |
| 8.11 | 136 | `memory/weekly_reviews/` | N'existe pas ; le rapport hebdo va dans `reports/weekly/week_AAAA_Wnn.md` | `scripts/cycle_weekly.py:100-105` | (compté en 6.7) |
| 8.12 | 142 | `EXCLURE_BOUCLES_STATS` « à 0 jusqu'au 28/10/2026 » | Date passée de 26 jours | `config.py:146` (défaut 0) ; même phrase `.env.example:93` | **À DÉCIDER** (suit 7.13) |
| 8.13 | 151-163 | Format du rapport : 9 titres | Le rapport produit aussi « Synthèse exécutive », « Pipeline en mode Prudent », « Registre des décisions » | `agents/orchestrator.py:161`, `agents/skills/pipeline_cache.py:125`, `utils/registre_ancre.py:24` | **GARDER** (corriger) |
| 8.14 | 177 | « Jamais de fichier > 200 lignes » | 12 fichiers Python dépassent | Voir §9 | **GARDER** (règle à tenir) |
| 8.15 | 191, 201, 65 | « LaunchAgent `com.alphasignal.dashboard` avec KeepAlive », « launchd (5 cycles + cleanup) » | 8 tâches du Planificateur Windows : 5 cycles, `cleanup`, `dashboard`, `surveillance` | `Get-ScheduledTask -TaskPath '\AlphaSignal\'` ; `surveillance` n'est citée par aucun document hors `docs/TODO.md` | **À DÉCIDER** (suit 5.2) |
| 8.16 | 22, 114 | « Max positions simultanées : 20 », « du `.env` » | Défaut du code : 5 ; variable absente de `.env.example` ; `README.md:136` écrit 5 | `config.py:50` | **GARDER** (corriger le README et `.env.example`) |
| 8.17 | 131 | `trade_journal.md` : « chaque trade » | Seulement les BUY/SELL du cycle quotidien | `git grep -n "enregistrer_signal("` → `agents/orchestrator.py:230` (et la démo) | **GARDER** (corriger) |
| 8.18 | 106 | « score = confiance × (1 + winrate/100) × urgence » | Un 4e facteur, `budget_boost`, toujours 1.0 | `arbitrator.py:27-28` ; voir 7.1 | **À DÉCIDER** (suit 7.1) |

Vérifié et exact dans `CLAUDE.md` : les 23 actifs de la watchlist (5 + 12 + 3 + 3,
`data/watchlist.json.exemple`), les 14 pages du dashboard, les 8 sous-agents, les 7 explorateurs, le
tableau des 4 modes du Budget Manager (`strategy.py:33-53`), `SEUIL_BUY`/`SEUIL_SELL`, les seuils de
confiance 8 / 9 / 4, les fréquences des cycles, les seuils 4 et 7 des explorateurs, les 5 de la queue,
les 8 actifs du tactical, la collecte (80 %, 3 essais, 5 min, 30 h), le cache CoinGecko de 10 min, le
prix frais de 15 min, l'anti-boucle de 24 h.

### 8.b `README.md`

| # | Ligne | Écrit | Réel | Preuve | Classement |
|---|---|---|---|---|---|
| 8.19 | 1, 53 | « AlphaSignal v4 », « Architecture v4 » | v5 | `CLAUDE.md:1` | **GARDER** (réécrire) |
| 8.20 | 36, 74 | Tactical « 30min » | 15 min | `scripts/install_tasks_windows.ps1:58` ; tâche `tactical` : `PT15M` | **GARDER** (réécrire) |
| 8.21 | 75 | Strategic : « Lancer les 7 explorateurs » | Le tactical les lance, pas le stratégique | `scripts/cycle_tactical.py:29-52` | **GARDER** (réécrire) |
| 8.22 | 36, 246 | « Installe 6 cycles », « plist (×6) » | 7 `.plist` ; 8 tâches Windows | `git ls-files 'scripts/*.plist'` → 7 | **GARDER** (réécrire) |
| 8.23 | 120-122, 252, 254 | « Dashboard (8 pages PWA) » | 14 pages | 14 routes de page, 15 gabarits avec `base.html` | **GARDER** (réécrire) |
| 8.24 | 134, 135, 140 | « Confiance min 7-8/10 », « R:R minimum 1:2 », DEFENSIF « conf 8 » | 8 (9 après 3 pertes, 4 en apprentissage) ; 1,2 ; 7 | `config.py:142-144` ; `risk_manager/manager.py:23` (`RR_MINIMUM = 1.2`) ; `strategy.py:39` | **GARDER** (réécrire) |
| 8.25 | 16-18, 102, 109-115, 203, 211-264 | 3 clés d'API ; `logs/launchd_*.log` ; rapport en 6 rubriques ; arborescence | Le code lit aussi `GEMINI_API_KEY`, `GROQ_API_KEY`, `TYPESAFE_API_KEY` ; logs `task_<nom>.log` ; l'arborescence omet `agents/chat`, `jev`, `knowledge`, `skills`, `technical_skills`, `vault`, `backtester` | `config.py:40-41,154` ; `install_tasks_windows.ps1:30` ; `git ls-files agents` | **GARDER** (réécrire) |

### 8.c `.env.example`

| # | Ligne | Écrit | Réel | Preuve | Classement |
|---|---|---|---|---|---|
| 8.26 | 25 | `RISK_PER_TRADE_PCT=50` | 2 (risque par trade, en %) | `config.py:48` : défaut `"2"`. 50 est la valeur de `MAX_CAPITAL_INVESTI_PCT` (`config.py:49`), absente du fichier : copier ce modèle donne 50 % de risque par trade. | **GARDER** (corriger en premier) |
| 8.27 | ensemble | — | 11 variables lues par le code manquent : `MAX_CAPITAL_INVESTI_PCT`, `MAX_POSITIONS_SIMULTANEES`, `SEUIL_CONFIANCE_PAPER`, `SEUIL_CONFIANCE_PAPER_DEFENSIF`, `SEUIL_CONFIANCE_LEARNING`, `ROTATION_ACTIVE`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `CHAT_HISTORIQUE`, `CHAT_HISTORIQUE_MAX_MIN`, `TAILSCALE_EXE_PATH` | Comparaison des `_get_optional` / `_get_required` / `os.getenv` du code avec les clés du fichier | **GARDER** (compléter) |
| 8.28 | 96-98 | `REPORT_TIME=07:30` (« Rapport quotidien ») | Sans effet : la valeur n'est qu'affichée | `git grep -n -w REPORT_TIME -- '*.py'` → `config.py:64,183` ; l'heure est dans la tâche planifiée | **SUPPRIMER** (variable et constante) — risque nul |

### 8.d `CLAUDE.md` des sous-dossiers

11 fichiers, pour la plupart inchangés depuis le premier commit du 04/05/2026.

| # | Fichier | Écarts | Classement |
|---|---|---|---|
| 8.29 | Les 11 `CLAUDE.md` de `agents/` | Détail ci-dessous | **À DÉCIDER** : les réécrire d'après le code, ou les supprimer et ne garder que le `CLAUDE.md` racine ? |

- `agents/budget_manager/CLAUDE.md:16-19` : confiance min 7 / 8 / 5 / 9 et max par trade 25 % en
  NORMAL → 4 / 7 / 3 / 8 et 10 % (`strategy.py:33,35,39,45,51`) ; l.44 « < 30€ » → 15 €
  (`arbitrator.py:19`) ; l.52 `budget_requests` → aucune table ni fichier (0 occurrence dans le code).
- `agents/analysts/risk_manager/CLAUDE.md:15,59` : « R:R < 1:2 → rejet » → 1,2 ; l.13 : max 5
  positions ; l.37 et l.39 : voir 7.14 et 7.15.
- `agents/analysts/fundamental_analyst/CLAUDE.md:8` : actions US par yfinance → Alpha Vantage
  (`analyst.py:80-83`) ; l.10-11, 26-27 : flux RSS Fed/BCE/BLS, DXY → 3 séries FRED (`macro.py:21-28`).
- `agents/analysts/sentiment_analyst/CLAUDE.md:9,27` : Fear & Greed actions (CNN) → non codé ;
  l.23-37 : format produit seulement sous `__main__` (`analyst.py:187`).
- `agents/analysts/market_analyst/CLAUDE.md:14-17` : 4H / Daily / Weekly → la décision n'utilise que
  le 1d (`asset_analyzer.py:28`).
- `agents/backtester/CLAUDE.md:1` : « Sous-Agent 5 » → absent des 8 sous-agents ; l.8-13 : 6 stratégies
  → 5 (`engine.py:70-76`) ; l.44-45 : dossiers `strategies/…` inexistants.
- `agents/trade_journalist/CLAUDE.md:1` : « Sous-Agent 6 » → n° 5 ; l.16-17, 46 : `real_trades.json` et
  rapport mensuel → aucun code ; l.42 : `SIG-001` → `SIG-0001` (`journalist.py:32`).
- `agents/explorers/CLAUDE.md:25` : « Max 30 actifs dans la watchlist » → aucune limite ; l.29-38 :
  une fréquence par explorateur → les 7 ensemble toutes les 15 min ; l.47 : « sauf trade ouvert » → la
  watchlist est toujours exclue (`explorers/base.py:68`).
- `agents/explorers/crypto_explorer/CLAUDE.md:4,8-10` : « Top 50-300 », 10 min, top 300 au
  stratégique → top 50, toutes les 15 min, jamais au stratégique.
- `agents/knowledge/CLAUDE.md:11-12` : `valuation.py`, `playbooks.py` → inexistants ; l.15-17 :
  8 sections à trois cycles → condensé du rapport quotidien seul (`rapport_pretrade.py:40`).
- `agents/technical_skills/CLAUDE.md:12-20` : skills 2 à 10 « (à venir) » → les 9 fichiers existent.

### 8.e `docs/` et le reste

| # | Document | Écrit → réel | Preuve | Classement |
|---|---|---|---|---|
| 8.30 | `docs/AVANT_ARGENT_REEL.md:40,154-164` | Condition 9, prix d'entrée paper : « pas fait » → fait (prix frais de moins de 15 min, anti-boucle 24 h) | `agents/paper_trader/prix_frais.py`, `anti_boucle.py` | **GARDER** (mettre à jour) |
| 8.31 | `docs/AVANT_ARGENT_REEL.md:32,50` | Q3.a : « lecture le 03/11/2026 », « en cours » → date passée de 20 jours | Dernière version du registre : v1.9 du 19/10 | **À DÉCIDER** : la lecture du 03/11 a-t-elle eu lieu, et où l'écrire ? |
| 8.32 | `docs/CONSOMMATION_API.md:33,34` | CoinGecko « sans cache » → cache de 10 min ; collecte « 23 × 3 » → 51 (5 cryptos × 3 + 18 × 2) | `fundamental_analyst/onchain.py:26-27` ; champ `timeframes` de `data/watchlist.json.exemple` | **GARDER** (mettre à jour) |
| 8.33 | `docs/HORIZONS.md:76-77,141-142` | Prix d'entrée = dernière barre, décision en attente → tranché et codé | Comme 8.30 | **GARDER** (mettre à jour) |
| 8.34 | `docs/DIAG_PRIX_ENTREE.md` | Diagnostic daté : options « non implémentées » → l'option 1 et le garde-fou le sont | Cité par le registre (l.681) et `AVANT_ARGENT_REEL.md:155` | **GARDER** (archive datée) |
| 8.35 | `docs/BROUILLON_RUPTURE_PRIX_ENTREE.md`, `docs/BROUILLON_CRITERE_EXPLORATEURS.md` | Brouillons dépassés : le premier (l.37-38) contredit `DIAG_PRIX_ENTREE.md:152-159` ; le second décrit des préalables faits depuis (`efb4003`) | Le premier n'est cité par aucun fichier ; le second par `docs/TODO.md:1027` | **À DÉCIDER** : les brouillons repris par le registre peuvent-ils partir ? |
| 8.36 | `docs/TAILSCALE.md:31-33,56-71` | « Le Mac », `brew`, `pmset` ; HTTPS par Serve « un jour » → déjà le seul accès ; `show_access_urls.py:95,106-108` affiche des adresses `http://<ip>:8080` que la doc dit mortes | `scripts/setup_tailscale.py:26,55` | **GARDER** (réécrire pour Windows) |
| 8.37 | `dashboard/templates/budget.html:75-77` (texte affiché) | « conf min 8 / 5 / 9 » (DEFENSIF / AGRESSIF / CONVICTION) → 7 / 3 / 8 | `agents/budget_manager/strategy.py:39,45,51` | **GARDER** (corriger) |
| 8.38 | `utils/scheduler_check.py:15` | `TACHES_WINDOWS` : 7 tâches → 8 en service (`surveillance` manque) | `Get-ScheduledTask` | **GARDER** (corriger) |
| 8.39 | `main.py:3` | « démarre le scheduler » → ne démarre rien | `main.py:30-33` | (compté en 1.1) |

## 9. Fichiers de plus de 200 lignes (règle 5)

Preuve : comptage des lignes de tous les fichiers suivis (`git ls-files`, hors images). 18 fichiers,
dont 12 de code Python.

| # | Fichier | Lignes | Classement | Remarque |
|---|---|---|---|---|
| 9.1 | `utils/real_portfolio_db.py` | 707 | **À DÉCIDER** | `docs/TODO.md` §32. Deux fonctions sans appelant (1.32). Quel découpage veux-tu, sachant que tout le portefeuille réel passe par ce fichier ? |
| 9.2 | `dashboard/api/routes.py` | 604 | **GARDER** (à découper) | 13 routes sans consommateur (§2) : leur retrait enlève environ 100 lignes. |
| 9.3 | `utils/indicators.py` | 334 | **GARDER** (à découper) | — |
| 9.4 | `utils/real_price.py` | 285 | **GARDER** (à découper) | Deux fonctions mortes (1.31). |
| 9.5 | `agents/orchestrator.py` | 276 | **GARDER** (à découper) | Une fonction morte (1.22). |
| 9.6 | `agents/decision_engine.py` | 270 | **GARDER** (à découper) | — |
| 9.7 | `utils/gemini.py` | 249 | **GARDER** (à découper) | Une fonction morte (1.29). |
| 9.8 | `scripts/check_after_update.py` | 249 | (voir 1.4) | — |
| 9.9 | `agents/analysts/market_analyst/analyst.py` | 218 | **GARDER** (à découper) | — |
| 9.10 | `agents/backtester/engine.py` | 214 | (voir 1.18) | — |
| 9.11 | `utils/heartbeat.py` | 212 | **GARDER** (à découper) | — |
| 9.12 | `agents/analysts/risk_manager/manager.py` | 204 | **GARDER** (à découper) | — |
| 9.13 | `dashboard/templates/real.html` | 550 | **GARDER** (à découper) | JS en ligne dans le gabarit. |
| 9.14 | `dashboard/templates/plans.html` | 255 | **GARDER** (à découper) | JS en ligne dans le gabarit. |
| 9.15 | `docs/TODO.md` (1 035), `docs/REGISTRE_CRITERES.md` (825), `README.md` (283), `CLAUDE.md` (201) | — | **GARDER** | Documents ; le registre est figé. Ce rapport dépasse aussi 200 lignes. |

## 10. Dépendances de `requirements.txt` jamais importées

Preuve : `git grep -n -w -E "(import|from) +<paquet>" -- '*.py'`.

| # | Dépendance | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 10.1 | `matplotlib>=3.7.0` | 0 import. Seule mention : `scripts/check_after_update.py:74` (liste de modules à vérifier). | **SUPPRIMER** | Faible ; ajuster cette liste si 1.4 est gardé. |
| 10.2 | `plotly>=5.15.0` | 0 import, 0 mention. | **SUPPRIMER** | Aucun. |
| 10.3 | `schedule>=1.2.0` | 0 import (les cycles sont des tâches planifiées). | **SUPPRIMER** | Aucun. |
| 10.4 | `pytz>=2023.3` | 0 import ; le code utilise `zoneinfo` (20 fichiers). | **SUPPRIMER** | Faible : `pytz` reste installé comme dépendance de yfinance. |
| 10.5 | `yfinance`, `requests`, `pandas`, `numpy`, `pandas-ta`, `python-dotenv`, `flask`, `google-genai`, `groq`, `typesafe-sdk` | Au moins un import chacun (`pandas_ta` : 1 fichier, `utils/indicators.py`). | **GARDER** | — |
| 10.6 | `tzdata` (absent du fichier) | `zoneinfo` en a besoin sous Windows ; il n'arrive que par pandas. | **À DÉCIDER** | L'écrire en toutes lettres dans `requirements.txt` ? |
| 10.7 | `graphifyy==0.9.79` (`requirements-dev.txt`) | Lancé par `scripts/regenerer_graphe.py:67` (`python -m graphify`). | **GARDER** | — |

## 11. Tests ignorés, ou qui testent du code mort

| # | Test | Preuve | Classement | Risque / question |
|---|---|---|---|---|
| 11.1 | `tests/test_topology.py` : 10 tests ignorés sans `graphify-out/graph.json` | `skipUnless(os.path.isfile(GRAPHE))` l.104 et 161 ; le fichier est hors git. Ils passent tous quand il est là (§0). | **GARDER** | Sur un clone neuf, ces tests ne tournent jamais : à savoir pour lire un « OK ». |
| 11.2 | Sauts conditionnels : Node (`test_dashboard_ecriture.py:132`, `test_page_audit.py:128`, `test_plan_racine.py:133`, `test_plan_sans_position.py:118`), PowerShell (`test_surveiller_dashboard.py:144`), Windows (`test_logs_rotation.py:130`), pandas (`test_jev_orchestrateur.py:40`) | `git grep -n -E "skipUnless" -- tests`. Aucun n'a sauté sur la tour (Node, PowerShell et pandas présents). | **GARDER** | — |
| 11.3 | `tests/test_purger_signaux_demo.py` (4 tests) | Teste le script ponctuel 1.8. | **À DÉCIDER** | Suit 1.8. |
| 11.4 | `tests/test_real_devise_migration.py` (7 tests) | Teste le script de migration 1.9. | **À DÉCIDER** | Suit 1.9. |
| 11.5 | `tests/test_sources_passage.py:79-80` | Appelle `agents.backtester.metrics.calculer_metriques`, module de 1.18. | **À DÉCIDER** | Suit 2.1. |
| 11.6 | Tests qui servent de référence à 1.32 (`test_real_conversion`, `test_real_sans_prix`, `test_real_devise`, `test_plan_sans_position`) | Appellent `get_real_budget_summary` et `progression_plan`, sans appelant en production. | **GARDER** (à réécrire avant 1.32) | — |
| 11.7 | `tests/test_fichiers_hors_git.py` | Cite `purger_signaux_demo.py` et `migrer_devise_reelle.py` : à ajuster si 1.8 ou 1.9 partent. | **GARDER** | — |
| 11.8 | Aucun `@unittest.skip` inconditionnel, aucun `expectedFailure` | `git grep -n -E "unittest\.skip\(\|expectedFailure" -- tests` → 0. | **GARDER** | — |

Outillage : `pytest` est installé dans le `.venv` et un dossier `.pytest_cache/` existe, mais la suite
se lance avec `unittest` et `pytest` n'est dans aucun fichier de dépendances.

## 12. Entrées de `docs/TODO.md` déjà faites ou devenues sans objet

44 entrées (2 blocs de tête, §1 à §42). Pour chacune, le correctif a été cherché dans le code actuel.
Ici **SUPPRIMER** veut dire : l'entrée peut sortir du fichier (ou partir dans une archive).

| § | Titre court | État | Preuve | Classement |
|---|---|---|---|---|
| Tête A | Décisions du tactical non persistées | Faite | `utils/registre_cycles.py:119` `enregistrer_decisions`, appelée `cycle_tactical.py:79`, `orchestrator.py:139`, `real_advisor.py:129`. | **SUPPRIMER** (reprendre le reliquat « BM en attente », `paper_trader/cycle.py:117`) |
| Tête B | `signal_results` jamais alimentée | Ouverte | Voir 4.3. | **GARDER** |
| 1 | Rotation des logs | Faite | `utils/logger.py:89,99` (`RotationTolerante`). | **SUPPRIMER** (reliquat : `logs/task_*.log` jamais bornés, `install_tasks_windows.ps1:30` écrit en `>>`) |
| 2 | Classement des erreurs LLM | En partie | Gemini fait (`utils/gemini_erreurs.py`) ; Groq classe encore par sous-chaîne (`utils/llm.py:184-187`). | **GARDER** (réduit à Groq) |
| 3 | Bandeau d'erreur du chat | Ouverte | `agents/chat/_llm.py:138`, texte fixe. | **GARDER** |
| 4 | Conseils réels chargés en entier | Ouverte | `context_builder.py:79` ; `_formatters.py:56` n'utilise que `len`. | **GARDER** |
| 5 | `metacognition_log.md` jamais une source | Note | Voir 6.6. | **À DÉCIDER** : déplacer cette règle dans un document permanent ? |
| 6 | Audit métacognitif des cycles | Faite, non barrée | `config.py:77` : éteint par défaut. | **SUPPRIMER** |
| 7 | Plafonds de `POST`/`PUT /api/plans` | En partie | `plans_routes.py:22` plafonne le POST ; le PUT (l.32) ne l'est pas. | **GARDER** (réduit au PUT) |
| 8 | P&L inconnu présenté comme 0 | En partie | Faits : `agents/chat/_pnl_latent.py:48-50`, `dashboard/api/queries.py:25-27`. Restent `real_portfolio_db.py:486`, `paper_trader/portfolio.py:45`, `chat/_extraction.py:135,151`. | **GARDER** (réduit) |
| 9 | Conseils réels tronqués | Faite | `real_advisor.py:29,95`. | **SUPPRIMER** |
| 10 | Code mort : skills, visualizer | Faite | Fichiers absents ; `scripts/graphify_modules.py:26` : `CODE_MORT = set()`. | **SUPPRIMER** |
| 11 | Rupture de série du 06/10 | Note | Portée par le registre (l.286). | **À DÉCIDER** : la retirer du TODO puisque le registre la porte ? |
| 12 | R:R constant à 2.0 | Ouverte | `position_sizer.py:43-57`. | **GARDER** |
| 13 | Interventions manuelles au registre | Faite, non barrée | `utils/registre_manuel.py` ; appels `routes.py:135,555,576,595`. | **SUPPRIMER** |
| 14 | Découvertes jamais analysées faute de prix | Ouverte | `explorers/base.py:68`, `fetch_data.py:116-123`. | **GARDER** |
| 15 | `_seuil_confiance_requis` | Ouverte | Voir 7.6. | **GARDER** |
| 16 | Settings réordonne la watchlist | Faite, non barrée | `dashboard/api/watchlist_io.py:26` ; `routes.py:49-50`. | **SUPPRIMER** |
| 17 | Fonctionnalités jamais appelées | Faite, titre non barré | `rapport_annexes.py:22-24`, `cycle_daily.py:39`. | **À DÉCIDER** : garder une ligne pour les catalyseurs et l'activation de la rotation ? |
| 18 | Le stratégique ne traite pas la queue | Faite | `cycle_strategic.py:1-7`. | **SUPPRIMER** |
| 19 | Explorateurs lancés deux fois | Faite | Aucun lancement dans `cycle_strategic.py`. | **SUPPRIMER** |
| 20 | Intuition force BUY après un veto | Ouverte | `intuition.py:101-102`, `decision_engine.py:161-166`. | **GARDER** |
| 21 | Veto Extreme Greed | Ouverte | Voir 7.8. | **GARDER** |
| 22 | Tactical : 8 premiers actifs | Ouverte | `cycle_tactical.py:160-161` (`[:8]`). | **GARDER** |
| 23 | Observation Jev « en attente du critère » | Sans objet | Critère commité (registre §7, l.380) ; observateur en place (`orchestrator.py:135,141`). | **SUPPRIMER** |
| 24 | Statistiques fictives jusqu'au 08/10 | Note | Portée par le registre (l.288). | **À DÉCIDER** : comme §11 |
| 25 | `setups_similaires` ne trouve rien | Ouverte | Voir 7.10. | **GARDER** |
| 26 | Winrate sans minimum de trades | Ouverte | `paper_trader/cycle.py:52`, `arbitrator.py:25,28`. | **GARDER** |
| 27 | Actifs sans fondamental, quota Alpha Vantage | En partie | Cache CoinGecko fait (`onchain.py:5-8`) ; `ACTIONS_US` = 5 tickers (`analyst.py:23`), aucun cache Alpha Vantage. | **GARDER** (réduit) |
| 28 | Tests Jev dans `logs/` | Faite | `isoler_journaux` dans 61 modules de test sur 62. | **SUPPRIMER** |
| 29 | 1 € = 1 $ (paper et fantôme) | Ouverte, gelée | `position_sizer.py:111-116`, `jev/fantome_regles.py:65`. | **GARDER** |
| 30 | Contrôles des plans hors cycle | Faite | `cycle_daily.py:38`. | **SUPPRIMER** |
| 31 | `plan_advisor`, clé « allocation » | En partie | `plan_advisor.py:45-48` ; `sous_repartition` non contrôlée (`plan_repartition.py:8`). | **GARDER** (réduit) |
| 32 | `real_portfolio_db.py` : 707 lignes | Ouverte | Voir §9 ; liste à compléter avec les 11 autres fichiers. | **GARDER** |
| 33 | D1, partie chat | Ouverte | `chat/_llm.py:43-44,62`, `_formatters.py:46-47` : « € ». | **À DÉCIDER** : la fenêtre de suivi de la consigne v2 est-elle close ? |
| 34 | Dashboard arrêté sans alerte | Faite | Le texte dit « reste ouvert jusqu'à l'installation » ; `Get-ScheduledTask` montre `\AlphaSignal\surveillance` installée, toutes les 5 min. | **SUPPRIMER** |
| 35 | Position réelle sans prix | Faite | `utils/real_conversion.py:34,102-104,140-142`. | **SUPPRIMER** (reliquat : 1.32) |
| 36 | Plan sans position : P&L de 0 | Faite | `real_conversion.py:21,66` ; `plans.html:84,95,152,155`. | **SUPPRIMER** |
| 37 | Clés d'API dans les logs | Faite | `utils/secret_mask.py:76`, `utils/logger.py:17,25`. | **SUPPRIMER** (reliquat : `check_health.py`/`check_status.py:133-134,149` mettent les clés dans l'URL et affichent l'exception par `print`) |
| 38 | Journal d'intuition jamais écrit | Faite | `decision_engine.py:190`, `intuition.py:153-170`. | **SUPPRIMER** |
| 39 | `memory/` hors git | Faite, non barrée | `git ls-files memory` → 4 `.exemple`. | **SUPPRIMER** (reliquat : 1.25) |
| 40 | Positions « boucle » | Faite | `paper_trader/portfolio.py:16`, `intuition_tracker.py:16`. | **SUPPRIMER** (reliquat : 7.13) |
| 41 | Collecte du 17/10 | Faite | `utils/collecte_verifiee.py:27,30` ; `cycle_daily.py:94,105`. | **SUPPRIMER** |
| 42 | Hygiène des explorateurs | En partie | Faits : `crypto_explorer/universe.py:26-33`, `queue_manager.py:4,31`. Reste `screening_helpers.py:31`. | **GARDER** (réduit) |

Références périmées relevées dans le TODO lui-même :

- §20 cite `agents/intuition.py:478-480` et `:425` ; le fichier fait 172 lignes (l'override est l.101-102).
- §23 : « orchestrator.py, 280 lignes » → 276. §32 : « routes.py, 616 » → 604.
- §27 : `onchain.py:19` → l.43 ; la coupure d'Alpha Vantage est dans `scripts/_chat_a_blanc.py:115-128`,
  pas dans `chat_cas_export.py`.
- Tête B : la démo n'est plus le bloc `__main__` de `performance_tracker.py` mais
  `agents/trade_journalist/demo_performance.py`.
- Une quinzaine de numéros de ligne ont glissé de 1 à 15 lignes (têtes A et B, §8, 9, 12, 13, 14, 15,
  20, 22, 25, 26, 30, 31, 40) : le code visé existe toujours.

## Synthèse

Un élément = une ligne de tableau classée (187 lignes ; les renvois « voir » et « compté en » ne sont
pas comptés deux fois).

| Section | SUPPRIMER | GARDER | À DÉCIDER |
|---|---|---|---|
| 1. Modules et fonctions | 16 | 8 | 11 |
| 2. Routes Flask | 3 | 0 | 4 |
| 3. Templates et statiques | 0 | 1 | 0 |
| 4. Tables SQLite | 2 | 3 | 1 |
| 5. Scripts | 0 | 2 | 1 |
| 6. `memory/` et `agents/knowledge/` | 1 | 8 | 2 |
| 7. Câblé à moitié | 0 | 2 | 13 |
| 8. Documentation | 1 | 26 | 10 |
| 9. Fichiers de plus de 200 lignes | 0 | 12 | 1 |
| 10. Dépendances | 4 | 2 | 1 |
| 11. Tests | 0 | 5 | 3 |
| 12. `docs/TODO.md` | 20 | 19 | 5 |
| **Total** | **47** | **88** | **52** |

Dans la section 8, 26 lignes « GARDER » sont des lignes de documentation à corriger, pas des lignes
justes. Plusieurs « À DÉCIDER » partagent la même question : les 52 lignes se ramènent à une
trentaine de décisions.

### Les trois suppressions les plus risquées

1. **1.32 — `get_real_budget_summary` et `progression_plan`** (`utils/real_portfolio_db.py`). Sans
   appelant en production, mais 4 modules de test s'en servent comme calcul de référence du
   portefeuille réel. Les supprimer sans réécrire ces tests fait disparaître la comparaison.
2. **2.6 — `POST /api/settings/watchlist`** (avec 2.5 et 2.7). La route réécrit toute la watchlist ;
   une ancienne page Settings en cache sur l'iPhone pourrait encore l'appeler, et sa suppression
   touche le libellé de registre `ROUTE_WATCHLIST`.
3. **1.1 — `main.py`**. Déclaré point d'entrée à trois endroits du code (carte Graphify, état du code,
   composants de la page Architecture) : la page Architecture et `tests/test_topology.py` sont à
   ajuster dans le même commit.

### Questions ouvertes hors tableaux

- **Q1 — Dépôt distant.** `origin/main` a été réécrit de force le 23/10/2026 et n'a plus d'ancêtre
  commun avec le `main` local (§0). Faut-il pousser `nettoyage` telle quelle (ce qui republie les
  161 commits locaux), ou d'abord réaligner le `main` local sur le dépôt distant ?
- **Q2 — Correction à faire avant tout nettoyage.** `.env.example:25` écrit `RISK_PER_TRADE_PCT=50`
  (8.26) : veux-tu la corriger tout de suite, hors du chantier de nettoyage ?
