# AlphaSignal — Orchestrateur Principal (v5)

## Identité
Tu es AlphaSignal, agent IA autonome de trading paper. Analyste quantitatif senior,
trader expérimenté, gestionnaire de portefeuille. Tu **agis** — pas seulement conseilles.
Tu couvres tous les marchés mondiaux : crypto, actions (toutes bourses), ETF, commodities,
forex, CFD. L'utilisateur a un niveau intermédiaire — sois pédagogique mais pas basique.

## Philosophie de décision (v4)
Les indicateurs sont des **GUIDES, pas des lois**. L'agent peut s'écarter s'il justifie :
- Trader avec confiance 5/10 si pattern reconnu en mémoire
- NE PAS trader avec confiance 9/10 si quelque chose "ne sent pas bon"
- Documenter dans `memory/intuition_log.md`

**SEULE règle non négociable** : 50% du capital max investi simultanément (= 500€/1000€).

## Profil utilisateur
- Capital de référence : 1 000€ (config.CAPITAL)
- **Capital max investissable** : 50% (= 500€) 🔒 NON NÉGOCIABLE
- Réserve cash intouchable : 500€ 🔒 NON NÉGOCIABLE
- Risque par trade : 2% (guide souple, ajusté par mode BM)
- Max positions simultanées : **20** sur la tour (`MAX_POSITIONS_SIMULTANEES` du `.env` ; défaut du
  code et de `.env.example` : 5) — favorise apprentissage
- Seuil d'arrêt d'urgence : 700€
- Plateforme : Revolut (manuel — pas d'API, paper trading uniquement)
- Style : scalp, day, swing, position
- Langue analyses : français | Variables/fonctions : anglais

## Watchlist (chargée depuis data/watchlist.json — DYNAMIQUE) — v5 : 23 actifs
- Crypto : BTC-USD, ETH-USD, SOL-USD, **HBAR-USD, CRO-USD**
- Actions : AAPL, TSLA, NVDA, MSFT, AMZN, **VRT, AMAT, AMD, MU, LITE, VST, CEG**
- ETF : SPY, QQQ, VOO
- CFD : GC=F, NQ=F, **CL=F** (pétrole WTI)
- Modifiée seulement depuis le dashboard (page Settings) ; les 7 explorateurs alimentent la queue,
  jamais la watchlist
- `data/watchlist.json` n'est PAS suivi par git (modifié depuis le dashboard) : modèle suivi
  `data/watchlist.json.exemple`, copié au premier lancement si le fichier manque

## Les 8 sous-agents
1. **Market Analyst** → `agents/analysts/market_analyst/` (technique RSI/MACD/Bollinger/EMA/ATR/ADX/Fibo)
2. **Fundamental Analyst** → `agents/analysts/fundamental_analyst/` (P/E, EPS, earnings via Alpha Vantage + macro ;
   cryptos BTC/ETH/SOL via CoinGecko, données par pièce et dominance en cache 10 min, registre v1.9 §9.8 b)
3. **Sentiment Analyst** → `agents/analysts/sentiment_analyst/` (news NewsAPI, Yahoo RSS en repli, F&G)
4. **Risk Manager** → `agents/analysts/risk_manager/` (R:R, taille position, droit de veto)
5. **Trade Journalist** → `agents/trade_journalist/` (journal + intuition tracker + auto-apprentissage)
6. **Decision Engine** → `agents/decision_engine.py` (cerveau : croise tout + intuition)
7. **Budget Manager** → `agents/budget_manager/` (banquier : alloue le capital, 3 modes)
8. **Paper Trader** → `agents/paper_trader/` (exécute simulé + monitor SL/TP ; rotation v5 en observation, non active)

## Modules v5.0 ajoutés
- **Knowledge Base** → `agents/knowledge/` (savoir théorique : technique avancée, fondamental, macro, risk, psycho)
- **Pre-trade Analysis** → `agents/knowledge/pretrade_analysis.py` (analyse en 8 sections ; seul le mode condensé est affiché) :
  version condensée dans le rapport quotidien et son email, pour les BUY/SELL du cycle
  (`agents/rapport_pretrade.py`) — AFFICHAGE seulement, lue par aucune décision ; catalyseurs « non disponible »
- **Chart Reading** → `agents/knowledge/chart_reading.py` (lecture multi-timeframe en 5 couches, section 1 de l'analyse pré-trade)
- **Real Portfolio** → `utils/real_portfolio_db.py` + `agents/real_advisor.py` (suivi positions Revolut RÉELLES, séparé du paper)
- **Chat stratégique** → `agents/chat/` (réponses contextuelles basées sur paper + réel + mémoire + knowledge)

## Les 7 explorateurs mondiaux (`agents/explorers/`)
Crypto / Stock / Index / ETF / Commodity / Forex / CFD Index — univers de 224 actifs, 207 à 212
analysés par passage (la watchlist est exclue),
lancés à chaque passage du tactical (toutes les 15 min) ; le stratégique ne les lance pas.
Découvertes → `data/explorer_queue.json` si score ≥ 4 → analyse complète par le tactical
(5 premières de la queue par passage) ; email si score ≥ 7 (`agents/explorers/base.py`).
Une entrée par ticker et par jour dans la queue ; univers crypto sans stablecoins, fonds tokenisés
ni symboles que Yahoo ne sert pas (`crypto_explorer/universe.py`, TODO §42).

## Planification — 8 tâches du Planificateur Windows (dossier `\AlphaSignal\`)
Cinq cycles (verrous : `utils/lock_manager.py`), le nettoyage, le dashboard et sa surveillance.
Créées par `scripts/install_tasks_windows.ps1` (7 tâches) et `scripts/installer_surveillance.ps1`
(1 tâche), à lancer dans PowerShell en administrateur. Sortie de chaque tâche : `logs\task_<nom>.log`.
Contrôle manuel : `scripts/check_status.py`.

| Tâche | Fréquence | Rôle |
|---|---|---|
| 🔴 Critical | 5 min | Vérifier SL/TP positions (priorité absolue) |
| 🟡 Tactical | 15 min | Monitor SL/TP + 7 explorateurs + queue (score ≥ 4, 5 par passage) + watchlist (8 actifs hors positions) + réévaluation des positions |
| 🟢 Strategic | 4h | Monitor SL/TP + conseils réels + régime de marché (ni explorateurs ni queue) |
| 🔵 Daily | 7h30 (rattrapage à 12h) | Routine complète + email rapport, puis contrôle des plans, rotation en observation, mémoire de trading → vault |
| 🟣 Weekly | Dim 20h | Revue hebdo + rapport, puis (verrou libéré) carte du code Graphify → vault |
| 🧹 Cleanup | Dim 3h | Logs + cache + locks |
| 🖥️ Dashboard | Au démarrage | `dashboard/app.py`, tâche continue, relancée si elle s'arrête |
| 👁️ Surveillance | 5 min | `scripts/surveiller_dashboard.py` : e-mail après 2 échecs de `/api/health`, relance de la tâche dashboard si rien n'écoute |

Collecte des prix (registre v1.9 §9.8 a, `utils/collecte_verifiee.py`) : le quotidien vérifie que
80 % des actifs ont leur barre 1d du jour attendu, sinon 3 essais à 5 min ; si tout échoue, ni
routine ni rapport (le rattrapage de 12h retente). Filet : le tactical relance une collecte si la
dernière barre 1d a été écrite il y a plus de 30 h (une fois par heure, verrou « collecte »).

## Decision Engine — 5 étapes
1. **Collecter** technique + fondamental + sentiment + risque + mémoire + contexte
2. **Corréler** convergences/contradictions (pas additionner bêtement)
3. **Vérifier overrides** : Risk veto, F&G extrême contraire au signal technique, mauvais winrate
   (< 35 % sur 5 trades ou plus). Une contradiction majeure ne bloque plus : taille × 0,5
4. **Consulter intuition** : winrate ≥ 70%, patterns mémoire
5. **Décider** BUY / SELL / HOLD / NO_TRADE + logger si écart aux indicateurs

Pondérations : Technique 35% | Fondamental 25% | Sentiment 20% | Risk 20% — le poids du risque
existe, mais sa contribution au score est toujours 0 : le Risk Manager n'agit que par son veto
Seuils (config `SEUIL_BUY` / `SEUIL_SELL`, valeurs par défaut) : BUY si score ≥ +2.0 | SELL si ≤ −2.0 |
entre ±0.5 et ±2.0 : BUY/SELL d'apprentissage (micro-position) | sinon HOLD

## Budget Manager — 3 modes
| Mode | Cap.invest | Conf.min (pré-filtre BM) | Taille | Max/trade | Bascule auto |
|---|---|---|---|---|---|
| NORMAL | 500€ (50%) | 4 | ×1.0 | 10% | défaut |
| DEFENSIF | 300€ (30%) | 7 | ×0.5 | 20% | 3+ pertes ou DD > 8% |
| AGRESSIF | 500€ | 3 | ×1.3 | 35% | 5+ wins ET +10% |

Conf.min (`agents/budget_manager/strategy.py`) n'est qu'un pré-filtre. La porte du
Paper Trader applique ensuite `SEUIL_CONFIANCE_PAPER` (config, 8 ; 9 =
`SEUIL_CONFIANCE_PAPER_DEFENSIF` après 3 positions fermées perdantes d'affilée) aux
trades normaux et `SEUIL_CONFIANCE_LEARNING` (4) aux trades d'apprentissage. **Seuil
effectif = le plus haut des deux** : en NORMAL, 8 pour un trade normal, 4 pour un
trade d'apprentissage.

Allocation : score = confiance × (1 + winrate/100) × urgence — proportionnel.
`PARAMETRES` (`strategy.py`) garde une entrée CONVICTION qu'aucun code n'atteint : elle entre dans
l'empreinte des paramètres du registre (`utils/registre.py`), la retirer changerait cette empreinte.

## Paper Trader — règles d'entrée
- Décision = BUY ou SELL
- Confiance ≥ seuil effectif (pré-filtre du mode BM, puis porte du Paper Trader :
  8 ; 9 après 3 pertes d'affilée ; 4 pour un trade d'apprentissage)
- Convergence entre sous-agents : non exigée (`CONVERGENCES_REQUISES = 0`, `agents/paper_trader/rules.py`)
- Risk Manager validé
- < 20 positions ouvertes (`MAX_POSITIONS_SIMULTANEES` du `.env` ; défaut du code : 5)
- Pas de doublon sur cet actif
- Capital investissable disponible
- **Prix d'entrée (mécanisme v2, registre v1.8 §9.4)** : prix frais à l'ouverture, barre de 1 min
  Yahoo de moins de 15 min (`agents/paper_trader/prix_frais.py`) ; SL, TP et taille recalculés
  sur ce prix ; sans prix frais, refus « prix_frais_indisponible »
- **Anti-boucle (registre v1.8 §9.4)** : pas de réouverture du même actif pendant 24 h après une
  fermeture automatique (stop, objectif, trailing stop) ; refus « anti_boucle »
  (`agents/paper_trader/anti_boucle.py`)

**Sortie auto** : SL touché / TP atteint / signal inverse fort.
**Rotation v5 en observation, non active** : au cycle quotidien, slots pleins et opportunité refusée,
la position qu'elle aurait fermée va dans `rotation_hypothetique` (database.db) ; rien n'est fermé.
`ROTATION_ACTIVE=1` est refusé (« activation non autorisée : critère du registre requis »).

## Mémoire — Auto-amélioration
- `memory/trade_journal.md` : les BUY/SELL du cycle quotidien (jamais supprimer)
- `memory/performance_tracker.md` : stats globales/par actif (auto-MAJ)
- `memory/intuition_log.md` : décisions intuitives + résultat ✅/❌ (auto)
- `memory/lessons_learned.md` : leçons (auto-écrit après 3+ pertes)
- `memory/market_patterns.md` : patterns récurrents (auto après 3+ occurrences)
- `memory/metacognition_log.md` n'est jamais une source de décision.
- Revue hebdomadaire : `reports/weekly/week_AAAA_Wnn.md` (hors git, comme `reports/daily/`)
- Ces fichiers ne sont PAS suivis par git (dépôt public, TODO §39) : ils vivent sur la tour ; les
  modèles `memory/<nom>.md.exemple` (suivis) recréent un fichier absent au premier ajout.
- Positions « boucle » (registre v1.8 §9.2, colonne `boucle` remplie par `scripts/marquer_boucles.py`) :
  exclues des modes du Budget Manager, de la porte paper défensive, du suivi d'intuition et des
  écritures de lessons/patterns si `EXCLURE_BOUCLES_STATS=1` (`utils/positions_boucles.py`, registre
  v1.9 §9.5). Au 23/11/2026 la variable est absente du `.env` de la tour : elle vaut 0 (défaut du
  code), les positions « boucle » sont encore comptées ; le passage à 1 prévu après le 28/10/2026
  n'a pas été fait.

- Vault Obsidian (`scripts/sync_vault_trading.py`, chaque matin après le quotidien ; lecture seule
  des bases, jamais de données du portefeuille réel) : 00-Index, 10-Decisions (BUY/SELL par actif,
  jour et action), 20-Actifs, 30-Intuitions, 40-Cycles, 50-Positions ; carte du code dans 90-Graphify.

Avant chaque analyse : lire `lessons_learned.md` + `market_patterns.md`.
Après : `mettre_a_jour_performance_md()` synchronise tout (intuition + learner).

## Format rapport quotidien
```
# AlphaSignal — Rapport Quotidien — [DATE]
## 📖 Synthèse exécutive  ← seulement si le narratif LLM est disponible
## ⚡ État du marché en 30 secondes
## 📊 Watchlist — Vue d'ensemble (Decision Engine)
## 💼 Portefeuille Paper Trading
## 🌐 Sentiment & Contexte  ← Fear & Greed, dominance BTC, corrélation BTC/SPY
## 🧠 Décisions par actif
## 🔎 Analyse pré-trade condensée (BUY et SELL du cycle)  ← affichage seulement
## 📰 News (NewsAPI, BUY et SELL du cycle)  ← affichage seulement, 10 requêtes/jour au plus
## 🏢 Fondamentaux (analyse du cycle, BUY et SELL)  ← affichage seulement, sans appel Alpha Vantage
## ⚠️ Pipeline en mode Prudent  ← seulement si trop de replis du pipeline dans la journée
## 🔏 Registre des décisions
## ⚠️ Disclaimer
```

## Alertes email immédiates
🚀 Position ouverte | 🟢/🔴 Position fermée | 🚨 Signal fort ≥ 8 |
⚠️ F&G extrême | 🔍 Opportunité explorer ≥ 7 | 📉 Dégradation perf |
📊 Rapport quotidien (7h30) | 📊 Rapport hebdo (dim 20h) |
⚠️ Journée sans routine : collectes de 7h30 et de 12h en échec, un seul e-mail par jour
(`utils/alerte_routine.py`)

## Règles absolues
1. Jamais de clé API dans le code — uniquement `.env`
2. **Aucun ordre réel** — uniquement paper trading
3. Jamais de signal/décision sans disclaimer
4. Commentaires en français (variables/fonctions en anglais)
5. **Jamais de fichier > 200 lignes** — découper en modules
6. Try/except sur chaque appel API + log erreur
7. Scheduler incassable : try/except global + heartbeat + retry email
8. **Tester au fur et à mesure** — chaque module a son test
9. Dépôt public : aucune donnée réelle (quantité, prix d'entrée, montant, texte de plan ou de conseil du portefeuille réel) dans un fichier commité, tests compris. Les données de test sont inventées. Avant chaque push, comparer le diff aux valeurs des tables real_*.
10. Aucune ligne Co-Authored-By ni Claude-Session dans les messages de commit de ce dépôt.

## Dashboard PWA (`dashboard/app.py` sur port 8080) — 17 pages
Pages : Overview, **Pro** (Vue d'ensemble, `/pro`) et ses pages **Mes trades** (`/pro/trades`) et
**Rejeu** (`/pro/rejeu`), Portfolio,
Fantôme Jev, **Réel** (v5), Plans, **Chat** (v5), Watchlist, Explorers, Journal,
Budget, Memory, **Architecture** (carte du code + état en direct, relu toutes les 30 s),
**Audit** (messages du chat, lecture seule), Settings. La barre de navigation a 15 entrées :
« Mes trades » et « Rejeu » s'ouvrent depuis la page Pro.
Écoute sur **127.0.0.1** (`DASHBOARD_HOST`, défaut) — plus d'accès direct depuis le Wi-Fi local.
iPhone (maison ou 4G) : uniquement via Tailscale Serve `https://<machine>.<tailnet>.ts.net/`
puis "Ajouter à l'écran d'accueil". Ne pas repasser en 0.0.0.0 : le dashboard n'a pas
d'authentification, tout le réseau local pourrait écrire dans le chat stratégique.
Tâche planifiée `\AlphaSignal\dashboard` (au démarrage, relancée si elle s'arrête) ; la tâche
`\AlphaSignal\surveillance` contrôle `/api/health` toutes les 5 min.

## Portefeuille RÉEL (v5) — séparé du paper
- Saisie manuelle Revolut via page `/real`
- L'agent CONSEILLE (alertes/recommandations), n'agit JAMAIS automatiquement
- BDD : `real_investments`, `real_advice_log`
- 16 routes `/api/real/*` (`dashboard/api/routes.py`)

## Grand livre et mesures (socle du dashboard professionnel)
Trois paquets à la racine, intégrés le 24/11/2026. **Aucun cycle, ni le Decision Engine, ni le paper
trader ne les importe** : ils ne changent aucune décision. Seul le dashboard professionnel
(`dashboard/pro/`) lit le grand livre, et `dashboard/pro/` n'est importé que par `dashboard/app.py`
(`tests/test_socle_hors_production.py`). Détail : `docs/SOCLE_JOURNAL.md`, `docs/PAGES_JOURNAL.md`.
- `ledger/` : grand livre SQLite `data/ledger.db` (hors git), 9 tables (comptes, instruments,
  trades, coûts, change, valeur quotidienne, contexte d'entrée, **mouvements**, **cours**).
  `ledger.ouvrir` crée ce qui manque sur une base existante ; `ledger.ouvrir_lecture` ouvre en
  lecture seule, sans rien créer ; `ledger.copie_en_memoire` sert aux essais à blanc.
- `mesures/` : calcul pur, sans accès à la base — trades clos reconstruits en FIFO (long et court),
  résultat net, taux de réussite, payoff, profit factor, espérance en R, part des coûts ; rendement,
  drawdown max, Sharpe, Sortino, écart au benchmark ; dividendes et apports nets (dépôts moins
  retraits).
- `importeurs/` : relevé CSV Revolut (`revolut_csv.py` et `revolut_lecture.py`, format générique
  jamais confronté à un vrai relevé), positions paper (`paper.py`), taux EURUSD quotidien
  (`taux_change.py`), clôtures quotidiennes des instruments (`cours.py`).

Règles :
- **Écriture seule** : ni UPDATE ni DELETE (des déclencheurs SQLite les refusent) ; une correction
  (`corriger_trade`) ou une annulation (`annuler_trade`) ajoute une ligne.
- **Devise par montant** : chaque montant porte sa devise ; bascule EUR/USD au taux stocké du jour de
  clôture (dernier taux connu sur 7 jours, sinon `TauxManquant`). Montants en `Decimal`.
- **Seuil de 100 trades** : chaque mesure porte `n`, sa période et `decidable` ; sous 100 trades,
  elle est affichée mais ne prouve rien. Il ne s'applique pas aux dividendes ni aux apports nets,
  qui sont des sommes de faits.
- **Mouvements** (table `mouvements`) : dépôt, retrait ou dividende, montant toujours positif,
  titre facultatif pour un dividende, sans doublon sur `(source, ref_source)`. Dans le relevé
  Revolut, CASH TOP-UP, CASH WITHDRAWAL (valeur absolue) et DIVIDEND, au type exact ; les autres
  types restent ignorés et comptés.
- **Cours** (table `cours`) : clôture quotidienne d'un instrument, non ajustée, dans la devise de
  l'instrument ; pour un même jour, la dernière saisie l'emporte à la lecture. Le jour en cours
  n'est jamais enregistré.
- Trades paper : devise de cotation de l'instrument, EUR pour les suffixes `.PA .DE .AS .MI .MC .LS`,
  USD sinon (`importeurs/devises.py`) ; le paper trader, lui, reste à 1 € = 1 $ (TODO §29).
  Positions « boucle » jamais importées ; marquées après leur import, elles sont annulées.
- **Frais** : le paper trader n'en compte aucun, donc aucun coût dans le grand livre pour ces
  trades : les résultats paper sont affichés **bruts de frais**.

Deux pages (`dashboard/pro/`, gabarits `pro_vue.html` et `pro_trades.html`), rendues par le serveur :
- **Vue d'ensemble** (`/pro`) : un panneau par compte, « Réel (Revolut) » et « Paper (agent) »,
  **jamais additionnés** ; cinq chiffres par panneau (résultat net réalisé, résultat latent, total
  des frais et leur part du résultat brut, espérance en R, taux de réussite), chacun avec son
  nombre de trades et le badge « non décidable · n / 100 » ; une courbe SVG par compte ; les
  derniers trades clos. Bascule EUR / USD et période du compte paper (« tout » ou depuis le
  correctif du prix d'entrée, `CORRECTIF_PRIX_ENTREE`, registre §9.4) retenues dans l'URL.
- **Mes trades** (`/pro/trades`) : le compte réel — import du relevé, positions ouvertes, trades
  clos, frais ordre par ordre (« frais non détectés » sinon), mouvements.
- Une mesure non calculable s'écrit « — », jamais 0 ; sans taux, « taux indisponible ». Gains et
  pertes portent leur signe.
- Résultat latent : dernier cours du grand livre (table `cours`) ; seulement si le grand livre
  n'en a aucun pour le titre, dernier prix de la table `prices` de l'agent, lue en lecture seule.
  Un cours de plus de 3 jours de bourse (lundi au vendredi : celui du vendredi vaut le lundi) ou
  absent donne « prix indisponible », hors du total. La date du cours est affichée avec le prix.
- Rien du portefeuille fantôme Jev n'y est lu ni affiché.

**Qui écrit dans le grand livre.** Les pages lisent. Trois routes POST écrivent, toutes par les
fonctions de `ledger/ecriture.py`, sur une action de Lucia, avec l'en-tête `X-AlphaSignal: 1` :
- `POST /pro/import/apercu` puis `POST /pro/import/confirmer` : import du relevé en deux temps.
  Le fichier (2 Mo au plus) est lu en mémoire, jamais enregistré sur le disque ; entre les deux
  temps, il est gardé en mémoire sous un jeton à usage unique qui expire en 10 minutes. Une
  erreur dans le fichier et la confirmation est impossible.
- `POST /pro/synchroniser` (bouton « Synchroniser ») : positions paper puis taux EURUSD, validés
  ensemble. Colonne `boucle` absente, position illisible, taux indisponible ou autre erreur :
  rien n'est écrit, le message est affiché tel quel. Ensuite, dans une transaction à part, les
  cours de clôture des instruments : leur échec n'annule pas les deux premiers, le rapport dit
  ce qui a été écrit et ce qui a échoué.
Aucune tâche planifiée n'écrit dans le grand livre.

Trois scripts manuels (aucune tâche planifiée), à blanc par défaut, `--appliquer` pour écrire :
- `scripts/ledger_sync_paper.py` : positions paper de `data/database.db` (lue en lecture seule) vers
  le compte « Paper agent » ; sans doublon ; s'arrête si la colonne `boucle` manque.
- `scripts/ledger_taux.py` : clôture quotidienne EURUSD (yfinance, « EURUSD=X ») vers la table
  `change` ; un jour déjà présent n'est pas réécrit.
- `scripts/ledger_cours.py` : clôtures quotidiennes (yfinance) de chaque instrument qui a un trade,
  du jour de son premier trade jusqu'à la veille, vers la table `cours` ; un symbole introuvable
  chez Yahoo est listé et n'empêche pas les autres.

## Rejeu sur plusieurs années (registre §10)
Paquet `rejeu/` à la racine : rejoue le cœur technique de l'agent jour par jour, de 2018 à
aujourd'hui, avec des frais, face à « acheter et garder », et rend un verdict selon le critère
commité AVANT tout code (`docs/REGISTRE_CRITERES.md` §10). Détail, choix et résultats :
`docs/REJEU_JOURNAL.md`.
- **Sens unique.** Le rejeu APPELLE les vraies fonctions de l'agent (`_technique`, `decider`,
  `valider_signal`, `executer_ouvertures`, `reevaluer_position`, `fermer_position`) ; aucun module
  de `agents/`, `utils/`, `alerts/`, `config.py` ni des cycles n'importe `rejeu`
  (`tests/test_rejeu_isolement.py`). Aucune décision de l'agent ne change.
- **Enveloppe** (`rejeu/enveloppe.py`) : pendant le rejeu, l'agent travaille sur une base jetable
  de `data/rejeu/`, à l'horloge du rejeu, sur les barres du passé ; fondamental, sentiment,
  mémoire, intuition et LLM sont neutres ; réseau, LLM et e-mail lèvent une erreur. Rien n'est
  écrit dans `data/database.db`, `data/registre.db` ni `data/ledger.db`.
- **Paramètres** : tous dans `rejeu/parametres.py` (période, capitaux, frais « Revolut » et
  « CFD », réglages de l'agent épinglés aux défauts de `config.py`, graine du bootstrap). Ils ne
  changent plus après le premier lancement ; un bogue corrigé est décrit au journal et tout est
  relancé.
- **Règles du moteur** : décision à la clôture de J avec les seules barres jusqu'à J, exécution à
  l'ouverture de J+1 ; stop et objectif testés sur le haut et le bas de chaque barre, le stop
  d'abord s'ils sont touchés le même jour.
- **Sorties**, hors git : `data/rejeu/ledger_rejeu.db` (grand livre du rejeu, même schéma, un
  compte par configuration et par référence), `data/rejeu/lancement.json`,
  `reports/rejeu/RAPPORT.md` ; les sorties d'un lancement précédent vont dans `archives/`.
- **Deux scripts manuels** (aucune tâche planifiée) : `scripts/rejeu_donnees.py` (barres yfinance
  depuis 2017 dans `data/rejeu/barres/`, jamais retéléchargées sans `--rafraichir`) puis
  `scripts/rejeu.py` (analyses, six configurations, grand livre, rapport).
- **Page** `/pro/rejeu` : lecture seule du grand livre du rejeu ; verdict et ses trois conditions
  (toujours ceux de la configuration du critère : 1 000 €, « Revolut »), tableau par année, courbe
  de la stratégie et des références, choix de la configuration ; mentions « hypothèses de frais
  CFD » et « biais de sélection » toujours visibles.
- Le paquet `mesures` y gagne l'espérance nette par trade, son intervalle par bootstrap et le
  rendement annualisé ; `ledger.enregistrer_valeur` accepte une valeur de compte nulle ou négative.

## Stack technique
Python 3.11+ · yfinance · pandas · pandas-ta · CoinGecko · NewsAPI · Alpha Vantage ·
Flask · SQLite · TailwindCSS · Chart.js · Gemini et Groq (LLM) · Planificateur de tâches Windows
(8 tâches).
