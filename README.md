# 📈 AlphaSignal v5

**Agent IA autonome de trading paper** : analyses multi-marchés (crypto, actions, ETF, matières
premières, forex, CFD), Decision Engine avec intuition, Budget Manager, dashboard PWA, registre
horodaté des décisions. Tourne sur une tour Windows, par le Planificateur de tâches.

> ⚠️ **Paper trading uniquement** — aucun ordre réel n'est exécuté. Toute analyse est à titre
> informatif et ne constitue pas un conseil financier. Le portefeuille réel (Revolut) est saisi à
> la main : l'agent conseille, il n'agit jamais.

Les règles détaillées de l'agent sont dans [CLAUDE.md](CLAUDE.md). Ce fichier dit comment
l'installer et le faire tourner.

---

## 🚀 Installation (Windows)

Depuis la racine du dépôt, dans PowerShell.

### 1. Environnement Python (3.11 ou plus)
```powershell
py -3 -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Configurer `.env`
```powershell
Copy-Item .env.example .env
```
Puis remplir `.env` :

| Variable | Rôle |
|---|---|
| `EMAIL_SENDER`, `EMAIL_APP_PASSWORD`, `EMAIL_RECIPIENT` | Obligatoires : envoi des rapports et des alertes (mot de passe d'application Gmail) |
| `NEWSAPI_KEY` | News du Sentiment Analyst (100 requêtes/jour) |
| `ALPHA_VANTAGE_KEY` | Fondamentaux des actions (25 requêtes/jour) |
| `GEMINI_API_KEY` | LLM du chat et des narratifs des rapports (20 requêtes/jour) |
| `GROQ_API_KEY` | LLM de repli, pipeline de raisonnement, conseiller réel |
| `TYPESAFE_API_KEY` | Observation Jev ; laisser vide tant que `JEV_OBSERVE` n'est pas à 1 |

Les autres réglages ont une valeur par défaut, écrite en commentaire dans `.env.example`.

### 3. Contrôle
```powershell
.venv\Scripts\python.exe scripts\check_status.py
```
Vérifie les tâches planifiées, le dernier rapport, le heartbeat, l'envoi d'e-mail et l'accès aux API.

### 4. Créer les tâches planifiées
Dans PowerShell ouvert **en administrateur** :
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_tasks_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\installer_surveillance.ps1
```
Le premier script crée 7 tâches, le second une huitième, dans le dossier `\AlphaSignal\` du
Planificateur. Le chemin du dépôt est écrit en tête des deux scripts (`$Root`) : l'adapter avant
de les lancer ailleurs que sur la tour.

### 5. Dashboard
La tâche `dashboard` le lance au démarrage de Windows. À la main :
```powershell
.venv\Scripts\python.exe dashboard\app.py
```
- Sur la tour : http://localhost:8080
- Depuis le téléphone : uniquement par Tailscale Serve, `https://<machine>.<tailnet>.ts.net/`
  (voir [docs/TAILSCALE.md](docs/TAILSCALE.md)), puis « Sur l'écran d'accueil » pour l'installer
  en PWA.

Le dashboard n'écoute que sur `127.0.0.1` (`DASHBOARD_HOST`). Il n'a pas d'authentification : ne
pas le passer en `0.0.0.0`.

---

## 🏗️ Architecture v5

### 8 sous-agents
| # | Agent | Rôle |
|---|---|---|
| 1 | Market Analyst | Analyse technique (RSI, MACD, Bollinger, EMA, ATR, ADX, Fibonacci) |
| 2 | Fundamental Analyst | Fondamentaux des actions (Alpha Vantage), cryptos (CoinGecko), macro |
| 3 | Sentiment Analyst | News (NewsAPI, Yahoo RSS en repli), Fear & Greed |
| 4 | Risk Manager | R:R, taille de position, droit de veto |
| 5 | Trade Journalist | Journal, suivi d'intuition, leçons et patterns |
| 6 | **Decision Engine** | Croise les analyses, applique les vetos, consulte l'intuition |
| 7 | **Budget Manager** | Alloue le capital, 3 modes (NORMAL, DEFENSIF, AGRESSIF) |
| 8 | **Paper Trader** | Exécute les trades simulés, surveille stops et objectifs |

Autour : 7 explorateurs (crypto, actions, indices, ETF, matières premières, forex, CFD d'indices ;
univers de 224 actifs), le chat stratégique, le conseiller du portefeuille réel, l'observation Jev,
le registre des décisions (`data/registre.db`, critères dans `docs/REGISTRE_CRITERES.md`) et le
vault Obsidian.

### 8 tâches planifiées (`\AlphaSignal\`)
| Tâche | Fréquence | Rôle |
|---|---|---|
| 🔴 `critical` | 5 min | Vérifier stops et objectifs des positions paper |
| 🟡 `tactical` | 15 min | Surveillance, 7 explorateurs, queue des découvertes, watchlist, réévaluation des positions |
| 🟢 `strategic` | 4 h | Surveillance, conseils sur le portefeuille réel, régime de marché |
| 🔵 `daily` | 7h30 (rattrapage à 12h) | Collecte vérifiée, routine complète, rapport par e-mail, vault |
| 🟣 `weekly` | Dimanche 20h | Revue hebdomadaire, puis carte du code |
| 🧹 `cleanup` | Dimanche 3h | Logs, cache, verrous |
| 🖥️ `dashboard` | Au démarrage | Dashboard Flask, relancé s'il s'arrête |
| 👁️ `surveillance` | 5 min | Contrôle du dashboard, e-mail après 2 échecs |

---

## 📋 Commandes utiles

```powershell
# Diagnostic
.venv\Scripts\python.exe scripts\check_status.py

# Lancer un cycle à la main
.venv\Scripts\python.exe -X utf8 scripts\cycle_critical.py
.venv\Scripts\python.exe -X utf8 scripts\cycle_daily.py

# État et relance des tâches
Get-ScheduledTask -TaskPath '\AlphaSignal\' | Select-Object TaskName, State
Start-ScheduledTask -TaskPath '\AlphaSignal\' -TaskName 'tactical'

# Journaux : un par tâche (logs\<nom>.log, erreurs dans logs\<nom>_errors.log),
# et la sortie brute de chaque tâche planifiée (logs\task_<nom>.log)
Get-Content logs\tactical.log -Tail 50 -Wait
Get-Content logs\task_daily.log -Tail 50

# Tests (réseau non requis)
.venv\Scripts\python.exe -m unittest discover -s tests
```

---

## 📊 Rapports et dashboard

### Rapport quotidien (e-mail à 7h30)
Synthèse exécutive (si le LLM répond), état du marché en 30 secondes, tableau de la watchlist,
portefeuille paper, sentiment et contexte (Fear & Greed, dominance BTC, corrélation BTC/SPY),
décisions par actif, puis en affichage seulement : analyse pré-trade condensée, news et
fondamentaux des BUY/SELL du cycle. Il se termine par l'état du registre et le disclaimer.
Copie dans `reports/daily/` (hors git).

### Rapport hebdomadaire (dimanche 20h)
Performance, portefeuille, statistiques d'intuition, Budget Manager. Copie dans `reports/weekly/`.

### Dashboard (16 pages)
Overview · Pro (vue d'ensemble) · Mes trades · Portfolio · Fantôme Jev · Réel · Plans · Chat ·
Watchlist · Explorers · Journal · Budget · Memory · Architecture · Audit · Settings

---

## 💰 Règles de gestion du capital

| Règle | Valeur | Statut |
|---|---|---|
| Capital de référence | 1 000 € | `CAPITAL` dans `.env` |
| **Capital investi au plus** | **50 % (500 €)** | 🔒 non négociable |
| Réserve de cash | 50 % (500 €) | 🔒 non négociable |
| Risque par trade | 2 % (20 €) | `RISK_PER_TRADE_PCT` |
| Confiance pour ouvrir une position paper | 8/10 ; 9 après 3 pertes d'affilée ; 4 pour un trade d'apprentissage | `SEUIL_CONFIANCE_*` |
| R:R minimum | 1,2 | Risk Manager |
| Positions simultanées | 5 par défaut | `MAX_POSITIONS_SIMULTANEES` (20 sur la tour) |

**Modes du Budget Manager** (pré-filtre de confiance, avant la porte du Paper Trader) :
- **NORMAL** par défaut : 50 % investissable, confiance 4, 10 % au plus par trade ;
- **DEFENSIF** après 3 pertes d'affilée ou un drawdown de plus de 8 % : 30 % investissable,
  confiance 7, tailles × 0,5 ;
- **AGRESSIF** après 5 gains d'affilée et +10 % : confiance 3, tailles × 1,3.

---

## 🧠 Intuition de l'agent

Le Decision Engine peut s'écarter des indicateurs :
- winrate d'au moins 70 % sur l'actif (3 trades ou plus) : confiance relevée ;
- pattern reconnu en mémoire : pressentiment renforcé ;
- winrate sous 35 % : prudence, jusqu'à annuler un BUY ou un SELL ;
- winrate fort et pattern réunis : un HOLD peut devenir un BUY d'apprentissage (micro-position).

Chaque écart est écrit dans `memory/intuition_log.md`, puis complété par son résultat.

---

## 🛠️ Dépannage

| Problème | Piste |
|---|---|
| `check_status.py` signale des tâches manquantes | Relancer les deux scripts d'installation en administrateur |
| Pas d'e-mail reçu | `logs\task_daily.log`, puis `logs\daily_errors.log` ; vérifier le mot de passe d'application Gmail |
| La tour était éteinte à 7h30 | La tâche rattrape au démarrage (`StartWhenAvailable`) et retente à 12h |
| Port 8080 occupé | Changer `DASHBOARD_PORT` dans `.env`, ou arrêter le processus qui l'occupe |
| Téléphone : `http://<ip>:8080` ne répond pas | Normal : passer par `https://<machine>.<tailnet>.ts.net/` |
| Cache à vider | `.venv\Scripts\python.exe -c "from utils.cache import vider; vider()"` |

---

## 📁 Structure

```
trading-agent/
├── CLAUDE.md                  ← règles de l'agent
├── config.py / .env.example / requirements.txt / requirements-dev.txt
│
├── agents/
│   ├── orchestrator.py        ← routine quotidienne
│   ├── decision_engine.py     ← décision (scores, vetos, intuition)
│   ├── asset_analyzer.py / intuition.py / memory_reader.py
│   ├── analysts/              ← market, fundamental, sentiment, risk_manager
│   ├── explorers/             ← 7 explorateurs, base, queue
│   ├── budget_manager/        ← strategy, arbitrator, manager
│   ├── paper_trader/          ← executor, monitor, rules, prix_frais, anti_boucle, rotation
│   ├── trade_journalist/      ← journal, performance, suivi d'intuition, learner
│   ├── skills/                ← pipeline de raisonnement LLM et son cache
│   ├── technical_skills/      ← régime de marché, qualité du setup, trailing stop, liquidité…
│   ├── knowledge/             ← base de connaissances, analyse pré-trade, lecture de graphique
│   ├── chat/                  ← chat stratégique et son audit
│   ├── jev/                   ← observation Jev et portefeuille fantôme
│   └── vault/                 ← notes du vault Obsidian
│
├── alerts/                    ← alert_manager, canal e-mail
├── dashboard/                 ← Flask : app.py, api/, pro/ (pages du grand livre), templates/ (16 pages), static/
├── scripts/                   ← cycle_*.py, cleanup.py, installateurs .ps1, outils manuels
├── utils/                     ← bases SQLite, registre, indicateurs, LLM, verrous, heartbeat, logs
├── tests/                     ← unittest
├── docs/                      ← registre des critères, TODO, notes de conception
│
├── data/                      ← watchlist.json.exemple suivi ; bases, cache et états hors git
├── memory/                    ← modèles *.md.exemple suivis ; fichiers de mémoire hors git
└── reports/                   ← rapports quotidiens et hebdomadaires, hors git
```

## 🔭 Améliorations futures

- [ ] Hébergement toujours allumé, indépendant de la tour
- [ ] ML pour la détection de patterns, au-delà des indicateurs classiques
- [ ] Connexion à un broker réel, avec confirmation manuelle obligatoire
- [ ] Notifications push sur iPhone
- [ ] Rejeu sur plusieurs années des règles réelles de l'agent (l'ancien backtester d'indicateurs a été retiré)
- [ ] Stock Explorer étendu aux bourses européennes et asiatiques

---

## ⚖️ Disclaimer

**AlphaSignal** est un outil d'aide à la décision en mode paper trading. Il ne constitue pas un
conseil financier. Les marchés comportent des risques de perte en capital. L'utilisateur est seul
responsable de ses décisions.
