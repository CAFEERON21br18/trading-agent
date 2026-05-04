"""
alerts/alert_manager.py — Gestionnaire d'alertes multi-canal
En V1 : email uniquement. Architecture prête pour Telegram/Discord en V2.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.logger                         import get_logger
from alerts.channels.email_channel        import envoyer_email, markdown_vers_html_simple

logger = get_logger(__name__)


def envoyer_rapport_quotidien(contenu_markdown: str, date_str: str) -> bool:
    """Envoie le rapport quotidien complet par email."""
    sujet = f"[AlphaSignal] Rapport quotidien — {date_str}"
    html  = markdown_vers_html_simple(contenu_markdown)
    return envoyer_email(sujet, contenu_markdown, corps_html=html)


def envoyer_alerte_signal_fort(ticker: str, direction: str, confiance: int,
                                 prix: float, details: str) -> bool:
    """Alerte immédiate quand confiance >= seuil (default 8/10)."""
    if confiance < config.ALERT_CONFIDENCE_THRESHOLD:
        return False
    sujet = f"🚨 [AlphaSignal] Signal fort {ticker} {direction} — confiance {confiance}/10"
    corps = (
        f"Signal détecté à confiance élevée.\n\n"
        f"Actif       : {ticker}\n"
        f"Direction   : {direction}\n"
        f"Prix        : {prix:,.4f}\n"
        f"Confiance   : {confiance}/10\n\n"
        f"{details}\n\n"
        f"⚠️  Exécution manuelle sur Revolut. Décision finale = utilisateur."
    )
    return envoyer_email(sujet, corps)


def envoyer_alerte_extreme_fear_greed(valeur: int, label: str) -> bool:
    """Alerte quand F&G < seuil_bas ou > seuil_haut."""
    if valeur < config.FEAR_GREED_EXTREME_LOW:
        sujet = f"⚠️ [AlphaSignal] Fear & Greed EXTRÊME BAS : {valeur} ({label})"
        corps = (
            f"Le Fear & Greed Index est à {valeur} ({label}), "
            f"sous le seuil de {config.FEAR_GREED_EXTREME_LOW}.\n\n"
            f"Signal contrarian potentiel : capitulation des acheteurs, "
            f"opportunités de longs à envisager (confirmer par technique)."
        )
    elif valeur > config.FEAR_GREED_EXTREME_HIGH:
        sujet = f"⚠️ [AlphaSignal] Fear & Greed EXTRÊME HAUT : {valeur} ({label})"
        corps = (
            f"Le Fear & Greed Index est à {valeur} ({label}), "
            f"au-dessus du seuil de {config.FEAR_GREED_EXTREME_HIGH}.\n\n"
            f"Signal contrarian potentiel : euphorie généralisée, "
            f"risque de correction / prises de bénéfices à envisager."
        )
    else:
        return False
    return envoyer_email(sujet, corps)


def envoyer_alerte_degradation(message: str) -> bool:
    """Alerte quand la performance de l'agent se dégrade."""
    sujet = "📉 [AlphaSignal] Alerte dégradation de performance"
    return envoyer_email(sujet, message)
