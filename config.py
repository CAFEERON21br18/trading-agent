"""
config.py — Configuration centralisée d'AlphaSignal
Charge et valide toutes les variables d'environnement au démarrage.
Lance une erreur claire si une variable obligatoire est manquante.
"""

import os
import sys
from dotenv import load_dotenv

# Chargement du fichier .env
load_dotenv()


def _get_required(key: str) -> str:
    """Récupère une variable obligatoire, lève une erreur si absente."""
    value = os.getenv(key)
    if not value:
        print(f"[ERREUR CONFIG] Variable obligatoire manquante : {key}")
        print(f"  → Copie .env.example en .env et remplis la valeur de {key}")
        sys.exit(1)
    return value


def _get_optional(key: str, default: str = "") -> str:
    """Récupère une variable optionnelle avec valeur par défaut."""
    return os.getenv(key, default)


# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_SENDER       = _get_required("EMAIL_SENDER")
EMAIL_APP_PASSWORD = _get_required("EMAIL_APP_PASSWORD")
EMAIL_RECIPIENT    = _get_required("EMAIL_RECIPIENT")
SMTP_HOST          = _get_optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT          = int(_get_optional("SMTP_PORT", "587"))

# ── APIs optionnelles ─────────────────────────────────────────────────────────
NEWSAPI_KEY         = _get_optional("NEWSAPI_KEY")
ALPHA_VANTAGE_KEY   = _get_optional("ALPHA_VANTAGE_KEY")
GEMINI_API_KEY      = _get_optional("GEMINI_API_KEY")
GROQ_API_KEY        = _get_optional("GROQ_API_KEY")

# ── Capital & Risk Management ─────────────────────────────────────────────────
CAPITAL                   = float(_get_optional("CAPITAL", "1000"))
RISK_PER_TRADE_PCT        = float(_get_optional("RISK_PER_TRADE_PCT", "2"))
MAX_CAPITAL_INVESTI_PCT   = float(_get_optional("MAX_CAPITAL_INVESTI_PCT", "50"))
MAX_POSITIONS_SIMULTANEES = int(_get_optional("MAX_POSITIONS_SIMULTANEES", "5"))
CAPITAL_STOP_THRESHOLD    = float(_get_optional("CAPITAL_STOP_THRESHOLD", "700"))

# Montants dérivés (calculés dynamiquement à partir du capital)
RISK_PER_TRADE_EUR  = CAPITAL * (RISK_PER_TRADE_PCT / 100)        # ex: 1000 × 2% = 20€
CAPITAL_INVESTISSABLE = CAPITAL * (MAX_CAPITAL_INVESTI_PCT / 100) # ex: 1000 × 50% = 500€
CASH_RESERVE        = CAPITAL - CAPITAL_INVESTISSABLE             # ex: 1000 - 500 = 500€

# ── Alertes ───────────────────────────────────────────────────────────────────
ALERT_CONFIDENCE_THRESHOLD = int(_get_optional("ALERT_CONFIDENCE_THRESHOLD", "8"))
FEAR_GREED_EXTREME_LOW     = int(_get_optional("FEAR_GREED_EXTREME_LOW", "20"))
FEAR_GREED_EXTREME_HIGH    = int(_get_optional("FEAR_GREED_EXTREME_HIGH", "80"))

# ── Rapport quotidien ─────────────────────────────────────────────────────────
REPORT_TIME = _get_optional("REPORT_TIME", "07:30")
TIMEZONE    = _get_optional("TIMEZONE", "Europe/Lisbon")

# ── Chemins des fichiers ──────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE    = os.path.join(BASE_DIR, "data", "watchlist.json")
DATABASE_FILE     = os.path.join(BASE_DIR, "data", "database.db")
MEMORY_DIR        = os.path.join(BASE_DIR, "memory")
REPORTS_DIR       = os.path.join(BASE_DIR, "reports")
LOGS_DIR          = os.path.join(BASE_DIR, "logs")

# Créer le dossier logs s'il n'existe pas
os.makedirs(LOGS_DIR, exist_ok=True)


def afficher_config():
    """Affiche un résumé de la configuration au démarrage."""
    print("=" * 60)
    print("  AlphaSignal — Configuration chargée")
    print("=" * 60)
    print(f"  Capital total          : {CAPITAL:.0f}€")
    print(f"  Capital investissable  : {CAPITAL_INVESTISSABLE:.0f}€ ({MAX_CAPITAL_INVESTI_PCT:.0f}%)")
    print(f"  Cash réserve           : {CASH_RESERVE:.0f}€ (intouchable)")
    print(f"  Risque par trade       : {RISK_PER_TRADE_PCT:.1f}% = {RISK_PER_TRADE_EUR:.2f}€")
    print(f"  Positions simultanées  : {MAX_POSITIONS_SIMULTANEES} max")
    print(f"  Seuil d'arrêt urgence  : {CAPITAL_STOP_THRESHOLD:.0f}€")
    print(f"  Rapport quotidien      : {REPORT_TIME} ({TIMEZONE})")
    print(f"  Email destinataire     : {EMAIL_RECIPIENT}")
    print(f"  NewsAPI                : {'✓ configurée' if NEWSAPI_KEY else '✗ non configurée (RSS utilisé)'}")
    print(f"  Alpha Vantage          : {'✓ configurée' if ALPHA_VANTAGE_KEY else '✗ non configurée'}")
    print(f"  Gemini (Google)        : {'✓ configurée' if GEMINI_API_KEY else '✗ non configurée'}")
    print(f"  Groq (fallback LLM)    : {'✓ configurée' if GROQ_API_KEY else '✗ non configurée'}")
    print("=" * 60)

    # Avertissement capital stop
    if CAPITAL <= CAPITAL_STOP_THRESHOLD:
        print(f"\n⚠️  ATTENTION : Capital ({CAPITAL}€) ≤ seuil d'arrêt ({CAPITAL_STOP_THRESHOLD}€)")
        print("   Les signaux sont SUSPENDUS. Met à jour CAPITAL dans .env.")


if __name__ == "__main__":
    afficher_config()
    print("\n✅ Configuration valide — AlphaSignal prêt à démarrer.")
