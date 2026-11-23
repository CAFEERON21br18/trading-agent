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
