"""
dashboard/api/topology_composants.py — Partie ÉCRITE À LA MAIN de la carte de l'agent (Phase 3).

Tout le reste (liens, lectures/écritures de tables, appels LLM, incohérences)
est calculé depuis le code (topology_sources.py, topology_build.py). Ici seulement :
- REGLES : quel module appartient à quel composant (préfixe de chemin, la
  première règle qui correspond gagne). Un module sans règle apparaît dans
  `non_classes` de /api/topology au lieu d'être ignoré ;
- COMPOSANTS : libellé, groupe (colonne de la carte), fréquence des cycles
  (elle vit dans les tâches planifiées, pas dans le code Python) ;
- TABLES suivies et ANNOTATIONS que le code ne peut pas prouver seul.
"""

# Groupes, dans l'ordre d'affichage (colonnes sur bureau, rangées sur mobile)
GROUPES = [
    ("cycles", "Cycles"),
    ("exploration", "Exploration"),
    ("analyse", "Analyse"),
    ("execution", "Exécution & conseil"),
    ("ressources", "LLM & données"),
]

# id -> (libellé, groupe, fréquence)
COMPOSANTS = {
    "cycle.critical": ("Critique", "cycles", "5 min"),
    "cycle.tactical": ("Tactical", "cycles", "15 min"),
    "cycle.strategic": ("Stratégique", "cycles", "4 h"),
    "cycle.daily": ("Quotidien", "cycles", "7h30"),
    "cycle.weekly": ("Hebdomadaire", "cycles", "dim. 20h"),
    "cycle.cleanup": ("Nettoyage", "cycles", "dim. 3h"),
    "dashboard": ("Dashboard", "cycles", None),
    "explorer.crypto": ("Explorateur Crypto", "exploration", None),
    "explorer.stock": ("Explorateur Actions", "exploration", None),
    "explorer.index": ("Explorateur Indices", "exploration", None),
    "explorer.etf": ("Explorateur ETF", "exploration", None),
    "explorer.commodity": ("Explorateur Matières", "exploration", None),
    "explorer.forex": ("Explorateur Forex", "exploration", None),
    "explorer.cfd_index": ("Explorateur CFD", "exploration", None),
    "explorers.base": ("Socle explorateurs", "exploration", None),
    "queue": ("Queue des découvertes", "exploration", None),
    "fetch_data": ("Collecte des prix", "exploration", None),
    "decision_engine": ("Decision Engine", "analyse", None),
    "analyst.market": ("Market Analyst", "analyse", None),
    "analyst.fundamental": ("Fundamental Analyst", "analyse", None),
    "analyst.sentiment": ("Sentiment Analyst", "analyse", None),
    "risk_manager": ("Risk Manager", "analyse", None),
    "technical_skills": ("Skills techniques", "analyse", None),
    "knowledge": ("Knowledge", "analyse", None),
    "pipeline": ("Pipeline groupé", "analyse", None),
    "pipeline_v1": ("Pipeline v1 (5 skills)", "analyse", None),
    "backtester": ("Backtester", "analyse", None),
    "budget_manager": ("Budget Manager", "execution", None),
    "paper_trader": ("Paper Trader", "execution", None),
    "journalist": ("Trade Journalist", "execution", None),
    "report.daily": ("Rapports", "execution", None),
    "real_advisor": ("Conseiller réel", "execution", None),
    "chat": ("Chat", "execution", None),
    "registre": ("Registre", "execution", None),
    "alerts": ("Alertes email", "execution", None),
    "llm.gemini": ("Gemini", "ressources", None),
    "llm.groq": ("Groq", "ressources", None),
}

# Composants calculés mais non affichés (reliés à tout, ils noieraient la carte)
MASQUES = {"infra", "outils", "llm.router"}

REGLES = [
    ("scripts/cycle_critical.py", "cycle.critical"),
    ("scripts/cycle_tactical.py", "cycle.tactical"),
    ("scripts/cycle_strategic.py", "cycle.strategic"),
    ("scripts/cycle_daily.py", "cycle.daily"),
    ("scripts/daily_routine.py", "cycle.daily"),
    ("scripts/cycle_weekly.py", "cycle.weekly"),
    ("scripts/cleanup.py", "cycle.cleanup"),
    ("scripts/fetch_data.py", "fetch_data"),
    ("scripts/", "outils"),
    ("main.py", "outils"),
    ("tests/", "outils"),
    ("dashboard/", "dashboard"),
    ("agents/explorers/crypto_explorer/", "explorer.crypto"),
    ("agents/explorers/stock_explorer/", "explorer.stock"),
    ("agents/explorers/index_explorer/", "explorer.index"),
    ("agents/explorers/etf_explorer/", "explorer.etf"),
    ("agents/explorers/commodity_explorer/", "explorer.commodity"),
    ("agents/explorers/forex_explorer/", "explorer.forex"),
    ("agents/explorers/cfd_index_explorer/", "explorer.cfd_index"),
    ("agents/explorers/queue_manager.py", "queue"),
    ("agents/explorers/", "explorers.base"),
    ("agents/asset_analyzer.py", "decision_engine"),
    ("agents/decision_", "decision_engine"),
    ("agents/intuition.py", "decision_engine"),
    ("agents/memory_reader.py", "decision_engine"),
    ("agents/analysts/market_analyst/", "analyst.market"),
    ("agents/analysts/fundamental_analyst/", "analyst.fundamental"),
    ("agents/analysts/sentiment_analyst/", "analyst.sentiment"),
    ("agents/analysts/risk_manager/", "risk_manager"),
    ("agents/analysts/", "infra"),
    ("agents/skills/pipeline.py", "pipeline_v1"),
    ("agents/skills/bayesien.py", "pipeline_v1"),
    ("agents/skills/base_rates.py", "pipeline_v1"),
    ("agents/skills/metacognition.py", "pipeline_v1"),
    ("agents/skills/pre_mortem.py", "pipeline_v1"),
    ("agents/skills/second_ordre.py", "pipeline_v1"),
    ("agents/skills/", "pipeline"),
    ("agents/technical_skills/", "technical_skills"),
    ("agents/knowledge/", "knowledge"),
    ("agents/backtester/", "backtester"),
    ("agents/budget_manager/", "budget_manager"),
    ("agents/paper_trader/", "paper_trader"),
    ("agents/trade_journalist/", "journalist"),
    ("agents/orchestrator", "report.daily"),
    ("agents/report_sections.py", "report.daily"),
    ("agents/real_advisor", "real_advisor"),
    ("agents/plan_advisor.py", "real_advisor"),
    ("utils/real_", "real_advisor"),
    ("agents/chat/", "chat"),
    ("agents/__init__.py", "infra"),
    ("utils/registre", "registre"),
    ("utils/gemini", "llm.gemini"),
    ("utils/llm.py", "llm.router"),
    ("utils/data_fetcher.py", "fetch_data"),
    ("utils/", "infra"),
    ("alerts/", "alerts"),
    ("config.py", "infra"),
]

# Tables SQLite suivies : nœuds « données » de la carte
TABLES = ["prices", "positions", "signals", "signal_results", "registre"]
# Fichiers de mémoire suivis (memory/) : lus par le Decision Engine
FICHIERS_MEMOIRE = ["performance_tracker.md", "lessons_learned.md", "market_patterns.md"]

# Ce que le code ne prouve pas seul (id de nœud -> note affichée)
ANNOTATIONS = {
    "table:prices": "Alimentée par la collecte, qui ne parcourt que la watchlist "
                    "(scripts/fetch_data.py) ; les explorateurs excluent la watchlist "
                    "(agents/explorers/base.py). Voir TODO §14.",
    "llm.groq": "Service externe (HTTP) appelé par utils/llm.py : pas de module Python.",
    "llm.gemini": "Réservé aux appelants de GEMINI_RESERVE_POUR. Valeur lue dans "
                  "config.py (défaut) : le .env de la tour peut la remplacer.",
}

# Références TODO des incohérences calculées
TODO_INCOHERENCES = {
    "explorateurs_sans_prix": "§14",
    "cycle_lit_queue_sans_analyse": "§18",
    "explorateurs_plusieurs_cycles": "§19",
    "table_sans_ecrivain_production": "PRIORITÉ HAUTE (signal_results)",
    "modules_orphelins": "§17",
    "code_mort": "§10",
    "llm_hors_routeur": "§10",
}


def composant(chemin):
    """Composant d'un fichier (chemin relatif, séparateur /), ou None sans règle."""
    for prefixe, cid in REGLES:
        if chemin.startswith(prefixe):
            return cid
    return None
