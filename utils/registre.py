"""
utils/registre.py — Registre des décisions des cycles (Phase 4, R1).

Une table unique `registre`, en ajout seul, dans un fichier séparé
(data/registre.db). Types de lignes : décision, réévaluation (seulement quand
quelque chose change), clôture de passage, jeu de paramètres, ancre quotidienne.
Chaque ligne porte l'empreinte de la précédente : une modification ou une
suppression après coup casse la chaîne (scripts/verifier_registre.py).
Des triggers interdisent UPDATE et DELETE, et refusent une ligne qui ne
prolonge pas la chaîne. Une écriture qui échoue est journalisée et comptée :
elle ne fait jamais échouer un cycle.
"""

import sys
import os
import uuid
import hashlib
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import config
from utils.logger import get_logger
from utils.registre_schema import (  # noqa: F401 (réexportés pour la vérification)
    GENESE, CHAMPS, COLONNES, SCHEMA, _canon, empreinte_ligne, _normaliser)

logger = get_logger(__name__)

CHEMIN = os.path.join(BASE, "data", "registre.db")


@lru_cache(maxsize=1)
def version_code() -> str | None:
    """Commit courant (12 caractères), lu dans .git sans lancer git (une fois par processus)."""
    try:
        git = os.path.join(BASE, ".git")
        if os.path.isfile(git):  # worktree : « gitdir: … »
            git = open(git, encoding="utf-8").read().split("gitdir:", 1)[1].strip()
        head = open(os.path.join(git, "HEAD"), encoding="utf-8").read().strip()
        if not head.startswith("ref: "):
            return head[:12]
        ref = head[5:]
        for racine in (git, os.path.dirname(os.path.dirname(git))):  # commondir d'un worktree
            if os.path.exists(os.path.join(racine, ref)):
                return open(os.path.join(racine, ref), encoding="utf-8").read().strip()[:12]
            if os.path.exists(os.path.join(racine, "packed-refs")):
                for l in open(os.path.join(racine, "packed-refs"), encoding="utf-8"):
                    if l.strip().endswith(" " + ref):
                        return l.split()[0][:12]
    except Exception:
        pass
    return None


def parametres_actifs() -> dict:
    """Paramètres qui influencent une décision (seuils, risque, pipeline, LLM)."""
    p = {k: getattr(config, k, None) for k in (
        "CAPITAL", "MAX_CAPITAL_INVESTI_PCT", "RISK_PER_TRADE_PCT", "MAX_POSITIONS_SIMULTANEES",
        "SEUIL_BUY", "SEUIL_SELL", "PIPELINE_FALLBACK_FACTOR", "PIPELINE_FALLBACK_ALERT",
        "METACOG_AUDIT_ENABLED", "GEMINI_RETRY_MAX_SEC", "CHAT_PRIX_AGE_MAX_MIN")}
    p["GEMINI_RESERVE_POUR"] = sorted(getattr(config, "GEMINI_RESERVE_POUR", []))
    try:
        from agents.decision_engine import POIDS, SEUIL_LEARNING, SEUIL_CONTRADICTION
        from agents.analysts.risk_manager.manager import RR_MINIMUM
        p.update(POIDS=POIDS, SEUIL_LEARNING=SEUIL_LEARNING, SEUIL_CONTRADICTION=SEUIL_CONTRADICTION,
                 RR_MINIMUM=RR_MINIMUM)
    except Exception as e:
        p["erreur_lecture"] = str(e)[:120]
    return p


def _connexion() -> sqlite3.Connection:
    conn = sqlite3.connect(CHEMIN, timeout=10, isolation_level=None)  # transactions explicites
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def _ajouter(conn, ligne: dict) -> str:
    """Insère une ligne au bout de la chaîne, sous verrou d'écriture (cycles concurrents)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        dernier = conn.execute("SELECT hash FROM registre ORDER BY id DESC LIMIT 1").fetchone()
        ligne["hash_precedent"] = dernier[0] if dernier else GENESE
        h = empreinte_ligne(ligne)
        conn.execute(f"INSERT INTO registre ({', '.join(COLONNES)}, hash) VALUES ({', '.join('?' * (len(COLONNES) + 1))})",
                     [ligne.get(c) for c in COLONNES] + [h])
        conn.execute("COMMIT")
        return h
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _ligne(type_: str, passage, ticker=None, champs=None, contenu=None, parametres=None) -> dict:
    return {"horodatage": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "type": type_,
            "cycle": passage.cycle if passage else None, "passage_id": passage.id if passage else None,
            "ticker": ticker, **_normaliser(champs or {}), "parametres": parametres,
            "version_code": version_code(), "contenu": _canon(contenu or {})}


class Passage:
    """Un passage de cycle : identifiant commun, compteurs, jeu de paramètres."""
    def __init__(self, cycle: str):
        self.cycle, self.id = cycle, uuid.uuid4().hex
        self.debut = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.ecrites = self.erreurs = 0
        self.parametres = None


def ouvrir_passage(cycle: str) -> Passage:
    return Passage(cycle)


def _empreinte_parametres(conn, passage: Passage) -> str:
    """Empreinte du jeu de paramètres ; ligne « parametres » à sa première apparition."""
    if passage.parametres is None:
        p = parametres_actifs()
        passage.parametres = hashlib.sha256(_canon(p).encode("utf-8")).hexdigest()[:16]
        if not conn.execute("SELECT 1 FROM registre WHERE type = 'parametres' AND parametres = ?",
                            (passage.parametres,)).fetchone():
            _ajouter(conn, _ligne("parametres", None, parametres=passage.parametres, contenu=p))
    return passage.parametres


def enregistrer(passage: Passage, type_: str, ticker: str, champs: dict | None = None,
                contenu: dict | None = None) -> bool:
    """Ajoute une décision ou une réévaluation. Ne lève jamais d'exception."""
    try:
        if type_ not in ("decision", "reevaluation"):
            raise ValueError(f"type {type_!r}")
        conn = _connexion()
        try:
            empreinte = _empreinte_parametres(conn, passage)
            _ajouter(conn, _ligne(type_, passage, ticker, champs, contenu, empreinte))
        finally:
            conn.close()
        passage.ecrites += 1
        return True
    except Exception as e:
        passage.erreurs += 1
        logger.warning(f"Registre : {type_} {ticker} non enregistrée : {e}")
        return False


def clore_passage(passage: Passage, attendues: int, details: dict | None = None) -> bool:
    """Ligne de fin de passage : décisions attendues, écrites, en erreur. Ne lève jamais."""
    try:
        conn = _connexion()
        try:
            _ajouter(conn, _ligne("passage", passage, contenu={
                "debut": passage.debut, "attendues": attendues, "ecrites": passage.ecrites,
                "erreurs": passage.erreurs, **(details or {})}))
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.warning(f"Registre : clôture du passage {passage.cycle} {passage.id} non enregistrée : {e}")
        return False
