# 📈 AlphaSignal v4

**Agent IA autonome de trading paper** — analyses quantitatives multi-marchés
(crypto, actions monde entier, ETF, commodities, forex, CFD), Decision Engine à
intuition, Budget Manager intelligent, dashboard PWA, 5 cycles d'exécution 24/7.

> ⚠️ **Paper trading uniquement** — aucun ordre réel n'est exécuté. Toute analyse
> est à titre informatif et ne constitue pas un conseil financier.

---

## 🚀 Démarrage rapide (5 étapes)

### 1. Configurer .env
```bash
cd ~/trading-agent
cp .env.example .env
# Éditer .env : email Gmail (mot de passe d'app), NewsAPI, Alpha Vantage
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Check initial
```bash
python scripts/check_status.py
```
Doit afficher 4-5 ✅ (yfinance peut être 429 rate-limited temporairement).

### 4. Activer les 5 cycles automatiques (launchd macOS)
```bash
./scripts/install_v4.sh install
```
Installe 6 cycles : **critical** (5min), **tactical** (30min), **strategic** (4h),
**daily** (7h30), **weekly** (dim 20h), **cleanup** (dim 3h).

### 5. Lancer le dashboard
```bash
python dashboard/app.py
```
- Ce PC : http://localhost:8080
- iPhone (Wi-Fi maison ou 4G) : via Tailscale Serve uniquement,
  `https://<nom-machine>.<tailnet>.ts.net/` (voir « Accès distant » plus bas)
  → Safari → Partager → "Ajouter à l'écran d'accueil" pour PWA

Le dashboard n'écoute que sur `127.0.0.1` (`DASHBOARD_HOST`, défaut) : il n'est
plus joignable directement depuis le Wi-Fi local (`http://<IP>:8080`).

---

## 🏗️ Architecture v4

### 8 sous-agents
| # | Agent | Rôle |
|---|---|---|
| 1 | Market Analyst | Analyse technique (RSI/MACD/Bollinger/EMA/ATR/ADX/Fibo) |
| 2 | Fundamental Analyst | Fondamentaux (P/E, EPS, earnings via Alpha Vantage) + macro |
| 3 | Sentiment Analyst | News (NewsAPI), Fear & Greed, **géopolitique** |
| 4 | Risk Manager | Validation R:R, taille de position, droit de veto |
| 5 | Trade Journalist | Journal + auto-apprentissage (patterns/leçons) |
| 6 | **Decision Engine** | Cerveau : croise tout + **intuition** (peut s'écarter) |
| 7 | **Budget Manager** | Banquier : alloue le capital intelligemment |
| 8 | **Paper Trader** | Exécute les trades simulés + monitor SL/TP + LOCK-IN |

### 7 explorateurs mondiaux
Crypto, Stock, Index, ETF, Commodity, Forex, CFD Index — scan ~180 actifs/run.

### 5 cycles + cleanup
| Cycle | Fréquence | Rôle |
|---|---|---|
| 🔴 Critical | 5 min | Vérifier SL/TP des positions |
| 🟡 Tactical | 30 min | Monitor + traiter queue d'opportunités fortes |
| 🟢 Strategic | 4h | Lancer les 7 explorateurs |
| 🔵 Daily | 7h30 | Routine complète + rapport email |
| 🟣 Weekly | Dim 20h | Revue hebdo + rapport |
| 🧹 Cleanup | Dim 3h | Logs + cache + locks |

---

## 📋 Commandes utiles

```bash
# Diagnostic du système
python scripts/check_status.py

# Lancer un cycle manuellement
./scripts/run_mac.sh critical
./scripts/run_mac.sh daily
./scripts/run_mac.sh weekly

# Installer / désinstaller les cycles automatiques
./scripts/install_v4.sh install
./scripts/install_v4.sh uninstall

# Vérifier les jobs launchd actifs
launchctl list | grep alphasignal

# Voir les logs
tail -f logs/alphasignal.log
tail -f logs/launchd_critical.log
```

---

## 📊 Comment lire les rapports

### Rapport quotidien (email à 7h30)
- ⚡ État du marché en 30s
- 📊 Tableau watchlist : technique + score + décision finale
- 💼 Portefeuille paper : capital, P&L, positions, mode BM
- 🌐 Sentiment & contexte : F&G, dominance BTC, **géopolitique**
- 🧠 Décisions par actif : convergences, contradictions, **intuition**
- ⚠️ Disclaimer paper trading

### Rapport hebdomadaire (dimanche 20h)
Performance + portefeuille + stats intuition + tableau Budget Manager.

### Dashboard (8 pages PWA)
🏠 Overview · 💼 Portfolio · 📡 Watchlist · 🔍 **Explorers** · 📔 Journal ·
💰 **Budget** · 🧠 Memory · ⚙️ Settings

---

## 💰 Règles de gestion du capital

| Règle | Valeur | Statut |
|---|---|---|
| Capital total | 1 000€ | configurable `.env` |
| **Capital max investissable** | **50% (500€)** | 🔒 NON NÉGOCIABLE |
| Réserve cash intouchable | 50% (500€) | 🔒 NON NÉGOCIABLE |
| Risque par trade (mode normal) | 2% (20€) | guide souple |
| Confiance min pour trader | 7-8/10 | guide souple |
| R:R minimum | 1:2 | guide souple |
| Max positions simultanées | 5 | guide souple |

**Modes du Budget Manager** :
- **NORMAL** par défaut
- **DEFENSIF** après 3+ pertes ou drawdown > 8% (→ 30% invest., conf 8)
- **AGRESSIF** après 5+ wins consécutifs ET +10% portefeuille
- **CONVICTION** manuel pour 1 trade exceptionnel (jusqu'à 40% du cap. invest.)

---

## 🧠 Intuition de l'agent

L'agent peut **s'écarter des indicateurs** s'il a un bon pressentiment :
- Winrate ≥ 70% sur cet actif → boost confiance
- Pattern reconnu en mémoire → boost score
- Contexte géopolitique aligné → boost
- Toute décision intuitive est tracée dans `memory/intuition_log.md`
  avec son **résultat rétroactivement** (✅/❌).

---

## 🌐 Accès distant (Tailscale Serve)

Le dashboard est accessible depuis n'importe où via le tailnet, en HTTPS,
sans exposition publique (pas de Funnel, pas de règle de pare-feu Windows
supplémentaire — Tailscale route via sa propre interface).

C'est aussi le seul accès depuis le téléphone, y compris à la maison : le
dashboard écoute sur `127.0.0.1` et Tailscale Serve proxifie HTTPS 443 →
`127.0.0.1:8080`. `DASHBOARD_HOST=0.0.0.0` rouvrirait l'accès Wi-Fi direct —
à éviter : le dashboard n'a pas d'authentification (chat stratégique compris).

**Prérequis**
- Tailscale installé et connecté sur la machine Windows (`tailscale status`)
- MagicDNS activé sur le tailnet
- Dashboard lancé (tâche `\AlphaSignal\dashboard` du Planificateur, déjà
  installée par `install_tasks_windows.ps1`)

**Activer**
```powershell
.venv\Scripts\python.exe scripts\setup_tailscale.py
```
Affiche l'URL finale, du type `https://<nom-machine>.<tailnet>.ts.net/`.
Idempotent : relancer le script ne duplique pas la configuration.

**Vérifier l'état**
```powershell
tailscale status          # le node est-il connecté ?
tailscale serve status    # qu'est-ce qui est actuellement partagé ?
```

**Désactiver**
```powershell
.venv\Scripts\python.exe scripts\teardown_tailscale.py
```
Retire tout le partage Tailscale Serve (équivalent à `tailscale serve reset`).

⚠️ Ne jamais utiliser `tailscale funnel` sur ce projet : cela exposerait le
dashboard (et donc le portefeuille paper/réel) publiquement sur Internet.

---

## 🛠️ Dépannage

| Problème | Solution |
|---|---|
| `check_status.py` ⚠️ partout | Vérifier `.env` (clés API + Gmail app password) |
| Pas d'emails reçus | `tail logs/launchd_daily.log` puis `cat logs/errors.log` |
| Mac dort à 7h30 | `RunAtLoad: true` dans le plist daily rattrape au réveil |
| Port 8080 occupé | `pkill -f dashboard/app.py` ou changer `DASHBOARD_PORT` |
| Téléphone : `http://<IP>:8080` ne répond plus | Normal (bind 127.0.0.1) → passer par `https://<nom-machine>.<tailnet>.ts.net/` |
| Cache pollué | `python -c "from utils.cache import vider; vider()"` |

---

## 📁 Structure

```
trading-agent/
├── CLAUDE.md                  ← orchestrateur principal (règles)
├── config.py / .env / requirements.txt / main.py
│
├── agents/
│   ├── orchestrator.py        ← coordination globale
│   ├── decision_engine.py     ← cerveau (corrèle + intuition)
│   ├── intuition.py / memory_reader.py / asset_analyzer.py
│   ├── analysts/              ← 4 sous-agents (technique/fond/sent/risk)
│   ├── explorers/             ← 7 explorateurs + base + queue + helpers
│   ├── budget_manager/        ← banquier (strategy/arbitrator/manager)
│   ├── paper_trader/          ← portfolio/executor/monitor/lockin/rules/cycle
│   └── trade_journalist/      ← journalist + perf_tracker + intuition_tracker + learner
│
├── data/
│   ├── watchlist.json / explorer_queue.json / lockin_assets.json
│   ├── heartbeat.json / database.db
│   └── cache/                 ← cache JSON par catégorie (TTL)
│
├── memory/
│   ├── trade_journal.md / performance_tracker.md
│   ├── intuition_log.md       ← auto-mis à jour
│   ├── lessons_learned.md     ← auto-mis à jour par learner
│   ├── market_patterns.md     ← auto-mis à jour par learner
│   └── weekly_reviews/
│
├── reports/{daily,weekly,unsent}/
│
├── scripts/
│   ├── cycle_{critical,tactical,strategic,daily,weekly}.py
│   ├── cleanup.py / check_status.py / check_health.py
│   ├── run_mac.sh / install_v4.sh
│   └── com.alphasignal.*.plist (×6)
│
├── alerts/
│   ├── alert_manager.py
│   └── channels/email_channel.py  ← retry + fallback
│
├── dashboard/                 ← Flask PWA (8 pages)
│   ├── app.py / api/{routes,queries}.py
│   ├── templates/ (8 pages)
│   └── static/ (CSS, JS, manifest PWA, icons)
│
└── utils/
    ├── data_fetcher.py        ← yfinance multi-marchés + auto-détection
    ├── cache.py               ← cache JSON par catégorie + TTL
    ├── lock_manager.py        ← anti-conflit cycles
    ├── heartbeat.py           ← détection panne
    ├── portfolio_db.py        ← SQLite paper trading
    └── database.py / indicators.py / helpers.py / logger.py
```

---

## 🔭 Améliorations futures

- [ ] Migration vers Oracle Cloud (toujours allumé, indépendant du Mac)
- [ ] ML pour détection de patterns (au-delà des indicateurs classiques)
- [ ] Connexion broker réel (avec confirmation manuelle obligatoire)
- [ ] Notifications push iOS via APNs
- [ ] Backtesting visuel dans le dashboard
- [ ] Stock Explorer étendu aux bourses européennes/asiatiques

---

## ⚖️ Disclaimer

**AlphaSignal** est un outil d'aide à la décision en mode paper trading.
Ne constitue pas un conseil financier. Les marchés comportent des risques de
perte en capital. L'utilisateur est seul responsable de ses décisions.
