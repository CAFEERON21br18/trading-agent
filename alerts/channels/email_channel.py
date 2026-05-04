"""
alerts/channels/email_channel.py — Envoi d'emails via SMTP Gmail
Utilise le mot de passe d'application configuré dans .env
"""

import sys
import os
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
from utils.logger import get_logger

logger = get_logger(__name__)

NB_TENTATIVES  = 3
DELAI_RETRY    = 30  # secondes entre tentatives
DOSSIER_UNSENT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports", "unsent",
)


def _envoi_smtp(sujet: str, corps_texte: str, corps_html: str | None, destinataire: str) -> None:
    """Une tentative d'envoi SMTP. Lève les exceptions naturellement."""
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"]    = config.EMAIL_SENDER
    msg["To"]      = destinataire
    msg.set_content(corps_texte)
    if corps_html:
        msg.add_alternative(corps_html, subtype="html")

    ctx = ssl.create_default_context()
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as serveur:
        serveur.starttls(context=ctx)
        serveur.login(config.EMAIL_SENDER, config.EMAIL_APP_PASSWORD)
        serveur.send_message(msg)


def _sauvegarder_localement(sujet: str, corps_texte: str) -> str:
    """Fallback : sauvegarde l'email dans reports/unsent/ pour ne pas le perdre."""
    try:
        os.makedirs(DOSSIER_UNSENT, exist_ok=True)
        horodatage = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        sujet_clean = "".join(c if c.isalnum() else "_" for c in sujet)[:60]
        chemin = os.path.join(DOSSIER_UNSENT, f"{horodatage}_{sujet_clean}.txt")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(f"SUJET : {sujet}\n\n{corps_texte}")
        logger.warning(f"Email sauvegardé localement : {chemin}")
        return chemin
    except Exception as e:
        logger.error(f"Échec sauvegarde locale email : {e}")
        return ""


def envoyer_email(sujet: str, corps_texte: str,
                  corps_html: str | None = None,
                  destinataire: str | None = None) -> bool:
    """
    Envoie un email via SMTP Gmail avec 3 tentatives et fallback local.
    Retourne True si succès, False sinon (mais le contenu est sauvé dans reports/unsent/).
    """
    destinataire = destinataire or config.EMAIL_RECIPIENT

    for tentative in range(1, NB_TENTATIVES + 1):
        try:
            _envoi_smtp(sujet, corps_texte, corps_html, destinataire)
            logger.info(f"Email envoyé à {destinataire} — sujet : {sujet}")
            return True
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Échec authentification SMTP (vérifie EMAIL_APP_PASSWORD) : {e}")
            break  # inutile de réessayer si l'auth échoue
        except Exception as e:
            logger.warning(f"Tentative {tentative}/{NB_TENTATIVES} échouée : {e}")
            if tentative < NB_TENTATIVES:
                time.sleep(DELAI_RETRY)

    _sauvegarder_localement(sujet, corps_texte)
    return False


def markdown_vers_html_simple(markdown: str) -> str:
    """Conversion minimaliste markdown → HTML pour l'email."""
    html = markdown
    # Entêtes
    for niveau, tag in [("### ", "h3"), ("## ", "h2"), ("# ", "h1")]:
        lignes = html.split("\n")
        for i, ligne in enumerate(lignes):
            if ligne.startswith(niveau):
                lignes[i] = f"<{tag}>{ligne[len(niveau):]}</{tag}>"
        html = "\n".join(lignes)

    # Gras **texte**
    while "**" in html:
        html = html.replace("**", "<b>", 1)
        if "**" in html:
            html = html.replace("**", "</b>", 1)

    # Convertir les sauts de ligne en <br>
    html = html.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
<html><body style="font-family: -apple-system, sans-serif; max-width: 800px; margin: auto; padding: 20px;">
<pre style="white-space: pre-wrap; font-family: 'SF Mono', Monaco, monospace; font-size: 13px;">
{markdown}
</pre></body></html>"""


if __name__ == "__main__":
    # Test : envoyer un email de test
    print("\nTest envoi email AlphaSignal...\n")
    succes = envoyer_email(
        sujet="[AlphaSignal] Test de connexion email",
        corps_texte="Ceci est un email de test envoyé par AlphaSignal. Si tu le reçois, la configuration SMTP fonctionne correctement.",
    )
    if succes:
        print(f"✅ Email envoyé à {config.EMAIL_RECIPIENT}")
    else:
        print("❌ Échec — vérifie les logs et le .env")
