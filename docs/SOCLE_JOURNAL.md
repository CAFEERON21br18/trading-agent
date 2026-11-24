# Socle du dashboard — journal d'intégration

Branche `socle-dashboard`, créée depuis `main` (09af052) dans un worktree séparé.

## Session du 24/11/2026 — aucun lot fait : la source est absente de la tour

### Constat

Le dossier source `Downloads\socle_dashboard` n'existe pas sur la tour. Sans lui, ni son `README.md`
ni le plan `docs/superpowers/plans/2026-11-22-socle-dashboard.md` ne sont lisibles, et les trois
paquets à copier (`ledger/`, `mesures/`, `importeurs/`) non plus.

Recherches faites, toutes sans résultat :

- le dossier `Downloads` (aucun élément créé ou modifié après le 19/11/2026, aucune archive récente) ;
- tout le disque `C:` (seul lecteur de la machine), fichiers cachés compris : aucun fichier ni dossier
  dont le nom contient « socle », aucun dossier `importeurs` ou `mesures`, aucun fichier dont le nom
  commence par `2026-11-22-` ;
- la corbeille ;
- le dépôt : aucune branche locale ou distante, aucun commit, aucun fichier suivi qui cite le socle,
  un grand livre ou ces paquets.

### Choix retenu (le plus prudent)

Rien n'a été inventé. Raisons :

- lot 1 : « copier sans changer la logique » n'a pas de sens sans l'original ; un grand livre écrit
  de mémoire serait un autre programme, présenté sous le nom du socle ;
- lot 2 : les 43 cas et leurs valeurs attendues sont dans les 5 fichiers de test de la source ;
- lots 3 et 4 : les deux adaptateurs écrivent dans le grand livre par son interface (compte,
  exécutions, contexte, table `change`). Les coder contre un schéma deviné donnerait du code à
  réécrire, avec des tests qui ne vérifient que ce schéma deviné ;
- lot 5 : les règles et les quatre points ouverts à reporter sont dans le README de la source.

Aucune question posée, aucune autre source cherchée hors de la tour (ni service en ligne, ni autre
machine) : la consigne désigne un dossier local.

### Ce qui a été fait

- Branche `socle-dashboard` et worktree `..\trading-agent-socle`. `main` et la copie de production
  ne sont pas touchés ; rien n'est écrit dans `data/` ; aucune tâche planifiée modifiée.
- Suite de référence dans ce worktree, réseau coupé : `Ran 459 tests` / `OK (skipped=10)`. Conforme
  à la référence de la consigne.
- Vérification demandée au lot 1 : `data/ledger.db` est couvert par `.gitignore` (règle `*.db`),
  ainsi que `data/ledger.db-wal` et `data/ledger.db-shm` (règles `*-wal`, `*-shm`). Un fichier
  `data/ledger.db-journal` (journal de transaction SQLite, hors mode WAL, présent le temps d'une
  écriture) ne l'est pas ; c'est déjà le cas pour `database.db`. `.gitignore` n'a pas été modifié.
- Ce journal. Aucun autre fichier.

La branche n'a pas été poussée : elle ne contient aucun lot. Voir « Écarts à la consigne ».

### Constats tirés du dépôt, utiles à la reprise

Tous vérifiés dans le code de `main` (09af052), sans ouvrir aucune base de `data/`.

**Lot 2 — tests**

- `tests/test_journaux_isoles.py` ne surveille que les paquets de sa liste `PAQUETS` (`agents`,
  `alerts`, `config`, `dashboard`, `scripts`, `tests`, `utils`). Un test qui importe `ledger`,
  `mesures` ou `importeurs` avant `isoler_journaux()` ne serait donc pas signalé. Les trois noms
  sont à ajouter à cette liste pour que la garde s'applique aux nouveaux tests.
- `dashboard/api/topology_composants.py` : `composant()` renvoie `None` pour un chemin sans règle
  dans `REGLES`, et aucune règle ne couvre `ledger/`, `mesures/` ni `importeurs/`.
  `test_tous_les_modules_classes` (`tests/test_topology.py`) exige une liste vide de modules non
  classés. Ce test fait partie des 10 ignorés sans `graphify-out/graph.json` : la suite ordinaire
  ne montrera pas l'oubli. Régénérer le graphe dans le worktree pour le vérifier
  (`python -m graphify extract . --code-only`, coût LLM nul), puis le retirer.
  Ajouter des règles à ce fichier ne fait importer les paquets par personne : c'est une table de
  préfixes de chemins.

**Lot 3 — adaptateur paper**

- Table `positions` (`utils/portfolio_db.py`) : `id`, `ticker`, `asset_type`, `direction`, `status`,
  `entry_price`, `entry_date`, `quantity`, `invested_amount`, `stop_loss`, `target_1`, `target_2`,
  `exit_price`, `exit_date`, `pnl_euros`, `pnl_percent`, `confidence`, `entry_reason`, `exit_reason`,
  `signals_used`, `created_at`. Colonnes ajoutées plus tard, absentes d'une base neuve :
  `trailing_stop_active`, `trailing_stop_price`, `atr_multiplier` ; `mecanisme_entree`,
  `prix_decision`, `prix_execution`, `age_prix_s` (`agents/paper_trader/prix_frais.py`) ; `boucle`
  (`scripts/marquer_boucles.py`).
- Statuts : `OPEN`, puis `CLOSED_SL`, `CLOSED_TP`, `CLOSED_TRAILING`, `CLOSED_REVERSAL`,
  `CLOSED_MANUAL`.
- **Frais : le paper trader n'en compte aucun.** Le résultat d'une position est
  `(exit_price − entry_price) × quantity` (inversé pour une vente à découvert), sans commission,
  écart de cours ni glissement, dans `utils/portfolio_db.py` comme dans `agents/paper_trader/` et
  `config.py`. C'est le cas « aucun coût » de la consigne.
- **Stop initial : la colonne `stop_loss`.** Elle est écrite à l'ouverture et aucun code ne la met à
  jour ensuite ; le trailing stop vit dans `trailing_stop_price`.
- **Positions « boucle »** : la définition (`utils/positions_boucles.REQUETE_IDS`) porte sur toute la
  table (au moins 3 positions de même ticker et de même `entry_price`). Deux conséquences pour un
  grand livre en écriture seule : la colonne `boucle` peut manquer (base jamais marquée) ou dater du
  dernier `marquer_boucles.py --appliquer` ; une position importée peut devenir « boucle » plus
  tard, si une troisième position identique apparaît. Point à trancher à la reprise : lire la
  colonne, ou recalculer l'ensemble par `REQUETE_IDS` au moment de l'import. Depuis le prix frais
  (mécanisme v2), deux prix d'entrée strictement égaux sont peu probables.
- **Devise** : la table `positions` n'a pas de colonne de devise, et ni `agents/paper_trader/` ni
  `utils/portfolio_db.py` ne convertissent. La règle « devise par montant » du socle demande donc
  une décision explicite sur la devise de `entry_price`, `exit_price` et `invested_amount`.
- Le mot « bras » n'apparaît nulle part dans le dépôt : le bras « regles » est défini par le socle.

**Lot 4 — taux de change**

- `utils/fx.py` lit déjà « EURUSD=X » par yfinance, pour le portefeuille réel : c'est un cours du
  moment gardé en mémoire, pas une clôture quotidienne, et il dépend de `utils/real_devise.py`.
  Ce n'est donc pas la source de l'importeur ; le plan de la source dira laquelle utiliser.
- Les tests du dépôt coupent le réseau par un proxy mort (`HTTP_PROXY=http://127.0.0.1:9`) et
  injectent la source de cours en paramètre (exemple : `prix_frais(ticker, telecharger=...)`).

### Pour reprendre

1. Copier le dossier `socle_dashboard` sur la tour, à l'endroit donné par la consigne.
2. Relancer la consigne sur la branche `socle-dashboard` existante (worktree `..\trading-agent-socle`),
   lots 1 à 5 inchangés.

### Écarts à la consigne

- Lots 1 à 5 : non faits, source absente.
- Poussée : non faite. La consigne demande de pousser la branche en fin de session ; avec ce seul
  journal, publier une branche sur le dépôt public n'apporte rien et reste à la main de Lucia
  (`git push -u origin socle-dashboard`).
- Tests : 459 lancés, 10 ignorés avant et après (un fichier de documentation ajouté, aucun code).

## Reprise du 24/11/2026 — la source est en place

Source lue en entier avant toute copie : `README.md`, le plan du 22/11/2026, 12 fichiers Python de
paquets, 6 fichiers de test. Aucun appel réseau, aucun sous-processus, aucune dépendance hors de la
bibliothèque standard. Suite d'origine lancée sur une copie hors du dépôt : `43 passed` (pytest,
Python 3.12).

Décisions de Lucia pour cette reprise : devise de cotation par suffixe de place (lot 3), lecture
de la colonne `boucle` à chaque synchronisation avec arrêt si elle manque et annulation des
positions marquées depuis (lot 3), paquets ajoutés à la garde des journaux et à la topologie
(lot 2), aucun coût pour les trades paper (lots 3 et 5).

### Lot 1 — les trois paquets

- Copiés à la racine, octet pour octet (empreintes SHA-256 comparées fichier par fichier) :
  `ledger/` (4 fichiers), `mesures/` (6), `importeurs/` (2). Aucune ligne modifiée.
- Plus long fichier : `ledger/ecriture.py`, 179 lignes.
- Non copiés : le `README.md` et le plan de la source (la consigne ne les demande pas ; leur contenu
  utile passe dans `CLAUDE.md` et `docs/TODO.md` au lot 5), `tests/` (réécrits au lot 2).
- `.gitignore` : `data/ledger.db`, `data/ledger.db-wal` et `data/ledger.db-shm` sont ignorés
  (`git check-ignore`). Fichier non modifié.
- Tests : `Ran 459 tests` / `OK (skipped=10)`, inchangé (aucun test ajouté à ce lot).
