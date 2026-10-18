"""
utils/vault_chemin.py — Dossier du vault Obsidian d'AlphaSignal.

Ordre : variable d'environnement ALPHASIGNAL_VAULT, puis la même clé dans le .env du dépôt
(lue seule, sans charger les autres variables), sinon %USERPROFILE%\\Documents\\AlphaSignalVault.
Utilisé par scripts/sync_graphify_vault.py, scripts/regenerer_graphe.py et la mémoire de
trading (scripts/sync_vault_trading.py). Aucun accès au disque hors lecture du .env.
"""

import os

VARIABLE = "ALPHASIGNAL_VAULT"
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_DEFAUT = os.path.join(os.path.expanduser("~"), "Documents", "AlphaSignalVault")


def dossier_vault(racine: str = RACINE) -> str:
    """Chemin absolu du vault (~ et %VARIABLES% développés)."""
    valeur = os.environ.get(VARIABLE)
    if not valeur:
        try:
            from dotenv import dotenv_values
            valeur = dotenv_values(os.path.join(racine, ".env")).get(VARIABLE)
        except Exception:
            valeur = None
    if not valeur or not valeur.strip():
        return VAULT_DEFAUT
    return os.path.abspath(os.path.expanduser(os.path.expandvars(valeur.strip())))
