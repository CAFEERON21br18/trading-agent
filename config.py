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
# Modèle de fallback Groq (voir utils/llm.py) : configurable car Groq retire
# régulièrement ses modèles (llama-3.3-70b-versatile puis compound-mini).
GROQ_MODEL          = _get_optional("GROQ_MODEL", "openai/gpt-oss-120b")

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

# ── Audit du chat (Phase 4) ───────────────────────────────────────────────────
# Rétention de message_audit en jours, purgée par le cycle cleanup (≤ 0 : jamais)
try:
    AUDIT_RETENTION_DAYS = int(_get_optional("AUDIT_RETENTION_DAYS", "90"))
except ValueError:  # valeur illisible : défaut plutôt qu'un arrêt de tous les cycles
    AUDIT_RETENTION_DAYS = 90

# ── Audit métacognitif Gemini (Phase 4 / Q1) ──────────────────────────────────
# Un appel Gemini par décision non-HOLD, résultat lu par aucun code (TODO §6).
# Désactivé par défaut ; toute valeur autre que 1/true/oui/yes = désactivé.
METACOG_AUDIT_ENABLED = _get_optional("METACOG_AUDIT_ENABLED", "false").strip().lower() in (
    "1", "true", "oui", "yes")

# ── Pipeline groupé : mode Prudent (Phase 4 / Q2) ─────────────────────────────
# Sans résultat du jour en cache et pipeline en échec : taille × ce facteur (0 à 1)
try:
    PIPELINE_FALLBACK_FACTOR = min(1.0, max(0.0, float(_get_optional("PIPELINE_FALLBACK_FACTOR", "0.5"))))
except ValueError:
    PIPELINE_FALLBACK_FACTOR = 0.5
# Alerte (heartbeat, rapport quotidien) au-delà de ce nombre de couples (ticker, action)
# DISTINCTS en fallback dans la journée
try:
    PIPELINE_FALLBACK_ALERT = int(_get_optional("PIPELINE_FALLBACK_ALERT", "5"))
except ValueError:
    PIPELINE_FALLBACK_ALERT = 5

# ── Réserve Gemini (Phase 4 / Q4) ─────────────────────────────────────────────
# Appelants de ask_llm(appelant=...) qui tentent Gemini (20 requêtes/jour) avant
# Groq ; les autres (pipeline, conseiller_reel…) vont directement à Groq.
# Liste vide = aucun. Un appel sans appelant garde l'ancien comportement.
GEMINI_RESERVE_POUR = frozenset(a.strip().lower() for a in _get_optional(
    "GEMINI_RESERVE_POUR", "chat,narratif_quotidien,narratif_hebdo").split(",") if a.strip())
# Q5 : 429 Gemini par minute → une seule nouvelle tentative si Google demande
# d'attendre au plus ce nombre de secondes (retryDelay) ; au-delà, repli Groq.
try:
    GEMINI_RETRY_MAX_SEC = max(0, int(_get_optional("GEMINI_RETRY_MAX_SEC", "10")))
except ValueError:
    GEMINI_RETRY_MAX_SEC = 10

# ── P&L latent du chat (Phase 4, TODO §8) ─────────────────────────────────────
# Âge maximum (minutes) du dernier prix relevé par les cycles ; au-delà, inconnu
try:
    CHAT_PRIX_AGE_MAX_MIN = max(1, int(_get_optional("CHAT_PRIX_AGE_MAX_MIN", "30")))
except ValueError:
    CHAT_PRIX_AGE_MAX_MIN = 30

# ── Decision Engine : seuils du score composite ───────────────────────────────
# BUY normal si score ≥ SEUIL_BUY, SELL normal si score ≤ SEUIL_SELL (négatif).
# Valeur illisible, ou de mauvais signe : défaut (+2.0 / −2.0).
try:
    SEUIL_BUY = float(_get_optional("SEUIL_BUY", "2.0"))
except ValueError:
    SEUIL_BUY = 2.0
SEUIL_BUY = SEUIL_BUY if SEUIL_BUY > 0 else 2.0
try:
    SEUIL_SELL = float(_get_optional("SEUIL_SELL", "-2.0"))
except ValueError:
    SEUIL_SELL = -2.0
SEUIL_SELL = SEUIL_SELL if SEUIL_SELL < 0 else -2.0

# ── Paper Trader : porte de confiance (Phase 4, P13) ──────────────────────────
# Filtre final avant ouverture (agents/paper_trader/rules.py), après le pré-filtre
# du Budget Manager (confiance_min du mode, agents/budget_manager/strategy.py) :
# le seuil effectif est le plus haut des deux. Valeurs appliquées jusqu'ici :
# 8 (tirée de ALERT_CONFIDENCE_THRESHOLD, désormais réservé aux alertes email),
# 9 après 3 positions fermées perdantes d'affilée, 4 pour un trade d'apprentissage.
SEUIL_CONFIANCE_PAPER          = int(_get_optional("SEUIL_CONFIANCE_PAPER", "8"))
SEUIL_CONFIANCE_PAPER_DEFENSIF = int(_get_optional("SEUIL_CONFIANCE_PAPER_DEFENSIF", "9"))
SEUIL_CONFIANCE_LEARNING       = int(_get_optional("SEUIL_CONFIANCE_LEARNING", "4"))

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
