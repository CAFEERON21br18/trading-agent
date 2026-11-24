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

### Lot 2 — les tests, en unittest

- Les 5 fichiers de test de la source sont réécrits sous le même nom : `tests/test_ledger.py`,
  `test_reconstruction.py`, `test_conversion.py`, `test_mesures.py`, `test_import_csv.py`.
  `tests/conftest.py` (propre à pytest) devient `tests/socle_fixtures.py`.
- 43 cas gardés, chacun avec ses valeurs attendues : 30 méthodes de test, dont 3 paramétrées
  devenues 16 sous-tests (7 tables, 5 et 4 montants). Compte vérifié par un lanceur qui compte
  les sous-tests : 30 − 3 + 16 = 43.
- `pytest.approx` devient `assertProche`, avec la même tolérance (relative 1e-6, absolue 1e-12).
  `pytest.raises(..., match=...)` devient `assertRaisesRegex`.
- Chaque base de test est un fichier d'un dossier temporaire, fermé avant la suppression du
  dossier. Le test paramétré sur les 7 tables ouvre une base neuve par table, comme la fixture
  d'origine. Rien dans `data/`, aucun `.env`, aucun réseau.
- Décision 3 de Lucia : `ledger`, `mesures` et `importeurs` sont ajoutés à `PAQUETS` de
  `tests/test_journaux_isoles.py` (un cas ajouté au test qui prouve la détection) ; chaque
  nouveau fichier de test appelle `isoler_journaux()` avant d'importer ces paquets.
- Topologie : trois règles dans `dashboard/api/topology_composants.py`, vers le composant
  `outils` (masqué, comme `scripts/` et `tests/`). Choix prudent : un composant visible aurait
  ajouté un nœud à la page Architecture et ses modules, que rien n'atteint en production,
  auraient été signalés orphelins (`test_incoherences_du_jour` l'interdit). C'est une table de
  préfixes : le dashboard n'importe pas les paquets. Vérifié avec un graphe régénéré dans le
  worktree (coût LLM nul, puis retiré) : `test_topology` 18 tests OK, aucun module non classé,
  mêmes trois incohérences qu'avant, aucun module du socle sur la carte.
- Ajout hors des 43 cas : `test_grand_livre_hors_git` (`tests/test_fichiers_hors_git.py`), qui
  garde `data/ledger.db` et ses fichiers WAL sous `.gitignore`.
- Tests : `Ran 490 tests` / `OK (skipped=10)` (459 + 30 + 1).
- Conséquence à connaître : dans le vault (90-Graphify), les modules de `mesures/` et
  `importeurs/revolut_csv.py` porteront le tag « orphelin » tant qu'aucun script ne les importe.
  C'est exact : rien ne s'en sert encore.

### Lot 3 — adaptateur paper

Fichiers : `importeurs/paper.py` (179 lignes), `importeurs/devises.py`, `scripts/ledger_sync_paper.py`,
trois fichiers de test et `tests/socle_paper_fixtures.py`.

- **Lecture seule** : la base de l'agent est ouverte par une URI `mode=ro` ; seule la table
  `positions` est lue. Un test compare l'empreinte du fichier avant et après. Le portefeuille
  fantôme Jev (`jev_paper_positions`) n'est jamais lu : un test le vérifie avec une table témoin.
- **Compte** « Paper agent », type `paper`, devise de compte EUR (capital de référence en euros).
- **Exécutions** : position `OPEN`, une exécution ; position `CLOSED_*`, deux. `ref_source` vaut
  `position-<id>-entree` et `position-<id>-sortie` : relancer n'ajoute rien, et une position
  ouverte qui se ferme n'ajoute que sa sortie. Sens : `LONG` achète puis vend, `SHORT` l'inverse.
- **Contexte de l'entrée** : bras `regles`, stop initial = colonne `stop_loss` (jamais mise à jour
  après l'ouverture). Un stop nul ou négatif est laissé vide, le grand livre refusant ces valeurs.
- **Frais** : le paper trader n'en compte aucun ; aucun coût n'est inscrit. Les résultats paper
  tirés du grand livre sont donc bruts de frais (écrit dans `CLAUDE.md` au lot 5).
- **Décision 1, devise** : `devise_cotation` rend EUR pour les suffixes `.PA .DE .AS .MI .MC .LS`,
  USD sinon. Le paper trader n'est pas corrigé. Une seconde fonction, `devise_incertaine`, signale
  sans rien changer les tickers pour lesquels ce USD par défaut est douteux ; le script les liste
  à la fin de son rapport.
- **Décision 2, positions « boucle »** : la colonne est lue à chaque synchronisation. Absente :
  `ColonneBoucleAbsente`, rien n'est importé, et le script s'arrête avant même d'ouvrir le grand
  livre (aucun fichier créé). Position importée puis marquée : `annuler_trade` sur chaque
  exécution encore active, donc une ligne d'annulation par exécution, aucune suppression ; testé
  (4 lignes d'origine toujours lisibles, 2 annulations, plus rien à la relance).
- **Tout ou rien** : une position illisible (direction ou statut inconnu, quantité ou prix non
  positif, position fermée sans prix ou date de sortie) et rien n'est écrit ; le rapport nomme
  la position.

Choix non couverts par la consigne, option prudente retenue :

- Le script est **à blanc par défaut**, comme `scripts/marquer_boucles.py` ; il faut `--appliquer`
  pour écrire. À blanc et sans grand livre existant, il travaille en mémoire et ne crée aucun
  fichier. Raison : une ligne écrite dans le grand livre ne s'efface plus.
- Une position annulée pour « boucle » puis démarquée ne serait pas réimportée : sa référence
  reste prise. Le cas ne devrait pas se produire (une série « boucle » ne rétrécit pas).
- Les dates sans fuseau sont lues comme UTC, ce que fait le grand livre ; le paper trader écrit
  ses dates en UTC avec décalage.
- La classe de l'instrument reprend `asset_type` de la position (`action`, `crypto`, `etf`, `cfd`).
- La base de test est créée par `initialiser_paper_db` (schéma réel, mode WAL) puis reçoit la
  colonne `boucle` comme le fait `marquer_boucles.py` : un changement de schéma du paper trader
  fera échouer ces tests au lieu de passer inaperçu.
- Ajout : `tests/test_socle_hors_production.py` lit le source et vérifie la règle centrale dans
  les deux sens (aucun module de l'agent, hors `scripts/ledger_*.py`, n'importe le socle ; le
  socle n'importe rien de l'agent). À ouvrir le jour où le nouveau dashboard lira le grand livre.

**Tickers dont la devise reste incertaine.** Le script n'a pas été lancé sur la base de
production : la liste qui suit vient des tickers cités dans le code (explorateurs, collecte,
modèle de watchlist), pas des positions réellement prises. Ils seraient enregistrés en USD par
défaut alors qu'ils ne sont pas cotés en dollars :

- indices hors États-Unis : `^FCHI ^GDAXI ^AEX ^IBEX ^FTMIB ^STOXX50E` (euros), `^FTSE` (livres),
  `^SSMI` (francs suisses), `^N225 ^HSI ^AXJO ^KS11 ^TWII ^NSEI ^BSESN ^TA125.TA` ;
- paires de change dont la devise de cotation n'est pas le dollar : `USDJPY=X USDCHF=X USDCAD=X
  EURGBP=X EURJPY=X GBPJPY=X AUDJPY=X EURAUD=X USDTRY=X USDZAR=X USDMXN=X USDBRL=X USDSGD=X
  USDINR=X`.

Aucun ticker du code ne porte un des six suffixes européens : aujourd'hui la règle ne rend EUR
pour aucun actif connu de l'agent. Le premier lancement à blanc sur la tour dira lesquels de ces
tickers figurent vraiment dans les positions ; une devise fausse se corrige ensuite par
`corriger_trade(devise=...)`, sans rien effacer.

Tests : `Ran 510 tests` / `OK (skipped=10)` (490 + 12 + 5 + 3).

### Lot 4 — taux de change EURUSD

Fichiers : `importeurs/taux_change.py` (93 lignes), `scripts/ledger_taux.py`, deux fichiers de test
et `tests/socle_taux_fixtures.py`.

- Source : yfinance, ticker « EURUSD=X », barres d'un jour ; le taux est en dollars pour un euro,
  comme l'attend la table `change`. `cloture_yfinance` est la seule fonction qui va en ligne, et
  `yfinance` n'y est importé qu'à l'appel : les paquets du socle restent utilisables sans lui.
- Sans doublon : un jour déjà présent dans la table n'est pas réécrit, même si la source donne
  une autre valeur (testé).
- Erreur de la source (réseau, réponse vide) : `SourceIndisponible`, le script sort en code 1,
  rien n'est écrit. Les journaux de l'agent ne sont pas utilisés : le socle n'importe pas
  `utils/`.
- Tests sans réseau : source simulée passée en paramètre ; `cloture_yfinance` elle-même est
  testée sur un faux module `yfinance` ; toute tentative de connexion lève une erreur.
- Rien n'est ajouté aux cycles planifiés ni aux tâches du Planificateur : outil manuel.

Choix non couverts par la consigne, option prudente retenue :

- **Le jour en cours (UTC) est écarté.** Sa barre n'est pas encore une clôture, et comme un jour
  présent n'est jamais réécrit, une valeur de milieu de journée serait restée pour toujours.
- Une valeur absente, nulle ou négative est écartée et listée dans le rapport, sans bloquer les
  autres jours.
- Les taux sont arrondis à 6 décimales : yfinance rend des flottants avec des chiffres de bruit
  au-delà.
- Période par défaut : de 7 jours avant le dernier taux stocké jusqu'à hier ; table vide,
  365 jours en arrière. `--depuis` et `--jusqu-a` la remplacent.
- Le script est à blanc par défaut, comme `ledger_sync_paper.py` : le cours est demandé à Yahoo,
  rien n'est écrit sans `--appliquer`.
- `utils/fx.py` n'est pas réutilisé : il sert un cours du moment au portefeuille réel et dépend
  de l'agent.

Reste vrai après ce lot : les week-ends et jours fériés n'ont pas de barre ; la bascule de
`mesures` reprend alors le dernier taux connu sur 7 jours (testé de bout en bout sur un trade
clos un dimanche).

Tests : `Ran 521 tests` / `OK (skipped=10)` (510 + 8 + 3).

### Lot 5 — documentation

- `CLAUDE.md` : section « Grand livre et mesures (socle du futur dashboard) », avant « Stack
  technique » : rôle des trois paquets, les trois règles (écriture seule, devise par montant,
  seuil de 100 trades), la règle de devise des trades paper, les deux scripts, et la mention
  demandée par Lucia : aucun coût pour les trades paper, résultats paper affichés bruts de frais.
- `docs/TODO.md`, nouveau §44. Le README de la source liste 6 points « à faire à l'intégration ».
  Quatre restent vrais et sont reportés : colonnes du relevé Revolut, frais du relevé, taux EURUSD
  quotidien, dépôts et retraits. Le point sur le taux est reformulé : le script existe désormais,
  mais rien ne le lance tout seul. Les deux autres sont faits (adaptateur paper, `.gitignore`) et
  le §44 le dit. S'y ajoutent les points nés de l'intégration (premier lancement sur la tour,
  devises incertaines, 1 € = 1 $ du paper trader, résultats bruts de frais, garde à ouvrir pour
  le futur dashboard).
- Relevé au passage, non corrigé (hors de ce lot) : `CLAUDE.md` situe encore les 16 routes
  `/api/real/*` dans `dashboard/api/routes.py` ; depuis le nettoyage du 23/11/2026 elles sont dans
  `routes_reel.py` et `routes_reel_saisie.py`.
- Tests : `Ran 521 tests` / `OK (skipped=10)`, inchangé (documentation seule).
