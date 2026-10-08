"""
scripts/_chat_a_blanc.py — Prompt d'une question NOUVELLE par le vrai chemin du chat, à blanc.

construire_cas(question) suit chat_engine.repondre jusqu'au prompt (intention →
context_builder → gabarit → _construire_prompt), sans appel LLM ni effet de bord.
a_blanc() garantit, le temps de la construction :
1. ni repondre ni enrichir_avec_gemini : ni LLM, ni chat_history, ni message_audit ;
2. database.DB_PATH pointe vers une copie jetable dans data/chat_cas/tmp/, supprimée
   en sortie, même en cas d'erreur ; une écriture SQL dans la copie est détectée
   (empreinte avant et après) et construire_cas refuse alors le cas ;
3. aucune écriture de cache (utils.cache.ecrire neutralisé ; le cache reste lu) ;
4. Alpha Vantage coupé : il n'a aucun cache, le fondamental des actions est donc
   « indisponible » ; la source est notée dans sources_coupees. News, CoinGecko,
   FRED, Fear & Greed et yfinance restent actifs ;
5. logs de production redirigés vers data/chat_cas/banc.log ;
6. filet : open() en écriture refusé dans le dépôt, hors de data/chat_cas/.
"""

import builtins
import contextlib
import gc
import glob
import hashlib
import os
import sqlite3
import time
import uuid
from unittest import mock

from scripts._banc_fichiers import DOSSIER_CAS, RACINE, journaux_detaches

_OPEN = builtins.open
SOURCE_ALPHA_VANTAGE = "alpha_vantage"


def _copier(source: str, cible: str) -> None:
    """Copie cohérente (API de sauvegarde SQLite), source ouverte en lecture seule."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(cible)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def empreinte(chemin: str) -> dict:
    """{table: sha256 de ses lignes} et le schéma : toute écriture SQL en change au moins une."""
    conn = sqlite3.connect(chemin)
    try:
        schema = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        out = {"(schéma)": hashlib.sha256(repr(schema).encode()).hexdigest()}
        for (nom,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            h = hashlib.sha256()
            for ligne in conn.execute(f'SELECT * FROM "{nom}"'):
                h.update(repr(ligne).encode())
            out[nom] = h.hexdigest()
        return out
    finally:
        conn.close()


def _supprimer(chemin: str) -> None:
    """Supprime la copie et ses fichiers annexes ; réessaie si une connexion traîne (Windows)."""
    restants = []
    for f in (chemin, f"{chemin}-wal", f"{chemin}-shm", f"{chemin}-journal"):
        for _ in range(10):
            try:
                if os.path.exists(f):
                    os.remove(f)
                break
            except PermissionError:
                gc.collect()  # ferme les connexions SQLite qui ne sont plus référencées
                time.sleep(0.2)
        if os.path.exists(f):
            restants.append(f)
    if restants:
        raise RuntimeError(f"copie jetable non supprimée : {restants} (nouvel essai au prochain lancement)")


def _purger(tmp: str) -> None:
    """Copies laissées par un arrêt brutal (meilleur effort)."""
    for f in glob.glob(os.path.join(tmp, "database_*.db*")):
        with contextlib.suppress(OSError):
            os.remove(f)


def _alpha_vantage_coupe(etat: dict):
    def coupe(function: str, symbol: str) -> dict:
        etat["sources_coupees"].add(SOURCE_ALPHA_VANTAGE)
        return {}  # même retour qu'une erreur Alpha Vantage : données « indisponibles »
    return coupe


def _garde_open(dossier_cas: str):
    racine = os.path.normcase(os.path.abspath(RACINE)) + os.sep
    autorise = os.path.normcase(os.path.abspath(dossier_cas)) + os.sep

    def garde(fichier, mode="r", *args, **kwargs):
        if isinstance(fichier, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
            chemin = os.path.normcase(os.path.abspath(os.fsdecode(fichier)))
            if chemin.startswith(racine) and not chemin.startswith(autorise):
                raise PermissionError(f"à blanc : écriture refusée ({chemin})")
        return _OPEN(fichier, mode, *args, **kwargs)
    return garde


@contextlib.contextmanager
def a_blanc(dossier_cas: str = DOSSIER_CAS):
    """Bloc sans effet de bord ; rend {copie, sources_coupees, ecritures_sql} (rempli en sortie)."""
    from utils import cache, database
    from agents.analysts.fundamental_analyst import alphavantage
    tmp = os.path.join(dossier_cas, "tmp")
    os.makedirs(tmp, exist_ok=True)
    _purger(tmp)
    copie = os.path.join(tmp, f"database_{uuid.uuid4().hex[:8]}.db")
    etat = {"copie": copie, "sources_coupees": set(), "ecritures_sql": []}
    try:
        _copier(database.DB_PATH, copie)
        avant = empreinte(copie)
        with contextlib.ExitStack() as pile:
            pile.enter_context(journaux_detaches(dossier_cas))
            pile.enter_context(mock.patch.object(database, "DB_PATH", copie))
            pile.enter_context(mock.patch.object(cache, "ecrire", lambda *a, **k: False))
            pile.enter_context(mock.patch.object(alphavantage, "_appel_av", _alpha_vantage_coupe(etat)))
            pile.enter_context(mock.patch.object(builtins, "open", _garde_open(dossier_cas)))
            yield etat
        gc.collect()
        etat["ecritures_sql"] = sorted(t for t, h in empreinte(copie).items() if avant.get(t) != h)
    finally:
        _supprimer(copie)


def construire_prompt(question: str) -> dict:
    """Mêmes étapes et mêmes arguments que chat_engine.repondre → enrichir_avec_gemini → ask_llm."""
    from agents.chat.chat_engine import _detecter_intention
    from agents.chat.context_builder import build_context
    from agents.chat._formatters import formater_par_intention
    from agents.chat._llm import SYSTEM_PROMPT, _construire_prompt
    intention = _detecter_intention(question)
    contexte = build_context(question)
    gabarit = formater_par_intention(intention, contexte)
    return {"intention": intention, "system": SYSTEM_PROMPT,
            "prompt": _construire_prompt(question, intention, gabarit, contexte)}


def construire_cas(question: str, dossier_cas: str = DOSSIER_CAS) -> dict:
    """Prompt construit à blanc ; lève si le chemin du chat a écrit dans la base (la copie)."""
    with a_blanc(dossier_cas) as etat:
        p = construire_prompt(question)
    if etat["ecritures_sql"]:
        raise RuntimeError("à blanc : le chemin du chat a écrit dans la copie jetable de la base ("
                           + ", ".join(etat["ecritures_sql"]) + ") ; rien en production, cas refusé")
    return {**p, "sources_coupees": sorted(etat["sources_coupees"])}
