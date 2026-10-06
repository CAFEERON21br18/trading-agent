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

## 10. Anciens skills : code mort, à supprimer (commit de nettoyage séparé)

- `agents/skills/pipeline.py` n'est importé par aucun module (remplacé par
  `pipeline_grouped.py`). Il est le seul à importer `bayesien.py`,
  `base_rates.py`, `metacognition.py`, `pre_mortem.py` et `second_ordre.py`,
  qui appellent `ask_gemini` en direct, hors de la réserve Gemini (Q4).
- Relevé le 06/10/2026 pendant Q4 : 0 appel en production. Ne pas les
  rebrancher tels quels ; vérifier les imports avant suppression.
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
