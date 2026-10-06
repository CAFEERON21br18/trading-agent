"""
utils/dernier_prix.py — Dernier prix relevé par ticker (Phase 4, TODO §8, option A).

Les cycles y déposent le prix qu'ils viennent de récupérer (aucun appel réseau
en plus) ; le chat le relit sans réseau. Un fichier par ticker, écrit de façon
atomique (fichier temporaire puis os.replace) : plusieurs cycles peuvent écrire
en même temps sans fichier tronqué ni mise à jour perdue entre tickers.
Un échec d'écriture est seulement journalisé : il ne fait jamais échouer un cycle.

Contenu : {ticker, prix, recupere_a (UTC), cours_a (horodatage de la barre
yfinance, avec fuseau de la place), seance (date de cette barre)}.
"""

import sys
import os
import re
import json
import math
import time
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

DOSSIER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "cache", "dernier_prix")
ESSAIS_REMPLACEMENT = 3   # Windows : refus possible si le chat lit le fichier au même instant


def _chemin(ticker: str) -> str:
    return os.path.join(DOSSIER, re.sub(r"[^A-Za-z0-9._-]", "_", ticker) + ".json")


def enregistrer(ticker: str, prix, horodatage_cours=None) -> None:
    """Dépose le prix relevé. Ne lève jamais d'exception."""
    tmp = None
    try:
        prix = float(prix)
        if math.isnan(prix) or prix <= 0:  # inconnu : on ne l'enregistre pas comme un prix
            logger.warning(f"Dernier prix {ticker} ignoré : valeur invalide ({prix})")
            return
        cours = horodatage_cours.isoformat() if hasattr(horodatage_cours, "isoformat") else None
        donnees = {"ticker": ticker, "prix": prix,
                   "recupere_a": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "cours_a": cours, "seance": cours[:10] if cours else None}
        os.makedirs(DOSSIER, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DOSSIER, prefix=".tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
        for essai in range(1, ESSAIS_REMPLACEMENT + 1):
            try:
                os.replace(tmp, _chemin(ticker))
                tmp = None
                return
            except PermissionError:
                if essai == ESSAIS_REMPLACEMENT:
                    raise
                time.sleep(0.05)
    except Exception as e:
        logger.warning(f"Dernier prix {ticker} non enregistré : {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def lire(ticker: str) -> dict | None:
    """Dernier prix relevé pour ce ticker, ou None (jamais relevé, illisible ou invalide)."""
    for essai in range(1, ESSAIS_REMPLACEMENT + 1):
        try:
            with open(_chemin(ticker), encoding="utf-8") as f:
                d = json.load(f)
            break
        except FileNotFoundError:
            return None
        except PermissionError as e:  # Windows : fichier remplacé par un cycle à cet instant
            if essai == ESSAIS_REMPLACEMENT:
                logger.warning(f"Dernier prix {ticker} illisible : {e}")
                return None
            time.sleep(0.05)
        except Exception as e:
            logger.warning(f"Dernier prix {ticker} illisible : {e}")
            return None
    prix = d.get("prix")
    if not isinstance(prix, (int, float)) or math.isnan(prix) or prix <= 0:
        return None
    return d
