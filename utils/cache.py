"""
utils/cache.py — Cache intelligent fichier JSON avec TTL par catégorie
Évite de spammer les APIs gratuites (yfinance, CoinGecko, NewsAPI, Alpha Vantage).

TTL par défaut :
- prix_ohlcv      : 5 min   (données de marché)
- news            : 30 min
- fondamentaux    : 24h     (P/E, EPS — change peu)
- geopolitique    : 1h
- macro           : 6h      (Fed Funds, CPI — change rarement)
- coingecko_top   : 1h      (top cryptos market cap)
- top_movers      : 10 min  (gainers/losers actions)
"""

import sys
import os
import json
import time
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache",
)

TTL_DEFAUTS = {
    "prix_ohlcv":     5 * 60,
    "news":           30 * 60,
    "fondamentaux":   24 * 3600,
    "geopolitique":   60 * 60,
    "macro":          6 * 3600,
    "coingecko_top":  60 * 60,
    "top_movers":     10 * 60,
}


def _chemin(categorie: str, cle: str) -> str:
    """Construit un chemin sûr pour le fichier cache."""
    cle_safe = hashlib.md5(cle.encode("utf-8")).hexdigest()[:16]
    dossier = os.path.join(CACHE_DIR, categorie)
    os.makedirs(dossier, exist_ok=True)
    return os.path.join(dossier, f"{cle_safe}.json")


def lire(categorie: str, cle: str, ttl_s: int | None = None) -> dict | None:
    """
    Retourne la valeur cachée si pas expirée, sinon None.
    ttl_s : durée de vie en secondes (par défaut, voir TTL_DEFAUTS).
    """
    ttl = ttl_s or TTL_DEFAUTS.get(categorie, 600)
    chemin = _chemin(categorie, cle)
    if not os.path.exists(chemin):
        return None
    try:
        age = time.time() - os.path.getmtime(chemin)
        if age > ttl:
            return None
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lecture cache {categorie}/{cle} échouée : {e}")
        return None


def ecrire(categorie: str, cle: str, valeur) -> bool:
    """Sérialise et stocke la valeur. Retourne True si OK."""
    chemin = _chemin(categorie, cle)
    try:
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(valeur, f, ensure_ascii=False, default=str)
        return True
    except Exception as e:
        logger.error(f"Écriture cache {categorie}/{cle} échouée : {e}")
        return False


def avec_cache(categorie: str, cle: str, fetcher, ttl_s: int | None = None):
    """
    Helper : retourne la valeur cachée OU appelle fetcher() et cache le résultat.
    fetcher : callable sans arguments qui retourne un dict/list JSON-sérialisable.
    """
    cached = lire(categorie, cle, ttl_s)
    if cached is not None:
        return cached
    try:
        val = fetcher()
    except Exception as e:
        logger.error(f"Fetcher {categorie}/{cle} échoué : {e}")
        return None
    if val is not None:
        ecrire(categorie, cle, val)
    return val


def vider(categorie: str | None = None) -> int:
    """Supprime tout le cache (ou seulement une catégorie). Retourne le nb fichiers supprimés."""
    cible = os.path.join(CACHE_DIR, categorie) if categorie else CACHE_DIR
    if not os.path.exists(cible):
        return 0
    n = 0
    for racine, _, fichiers in os.walk(cible):
        for f in fichiers:
            try:
                os.remove(os.path.join(racine, f))
                n += 1
            except Exception:
                pass
    logger.info(f"Cache vidé : {n} fichiers supprimés ({categorie or 'tout'})")
    return n


def stats() -> dict:
    """Retourne nb de fichiers + taille totale par catégorie."""
    if not os.path.exists(CACHE_DIR):
        return {}
    res = {}
    for cat in os.listdir(CACHE_DIR):
        chemin_cat = os.path.join(CACHE_DIR, cat)
        if not os.path.isdir(chemin_cat):
            continue
        fichiers = os.listdir(chemin_cat)
        taille = sum(os.path.getsize(os.path.join(chemin_cat, f)) for f in fichiers)
        res[cat] = {"fichiers": len(fichiers), "taille_ko": round(taille / 1024, 1)}
    return res
