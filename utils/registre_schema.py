"""
utils/registre_schema.py — Schéma et empreintes du registre des décisions (Phase 4, R1).

Partagé par l'écriture (utils/registre.py) et la vérification
(scripts/verifier_registre.py) : une ligne est hachée exactement comme elle
sera relue dans SQLite (types normalisés, JSON canonique).
"""

import json
import hashlib

from utils.valeurs import nombre_ou_none

GENESE = "0" * 64
CHAMPS = ("decision", "style", "score", "confiance", "prix", "position_id")
COLONNES = ("horodatage", "type", "cycle", "passage_id", "ticker", *CHAMPS,
            "parametres", "version_code", "contenu", "hash_precedent")
_ENTIERS, _REELS = ("confiance", "position_id"), ("score", "prix")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS registre (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('decision', 'reevaluation', 'passage', 'parametres', 'ancre')),
    cycle TEXT CHECK (cycle IN ('tactical', 'quotidien', 'strategique', 'critique', 'manuel')),
    passage_id TEXT, ticker TEXT, decision TEXT, style TEXT, score REAL, confiance INTEGER,
    prix REAL, position_id INTEGER, parametres TEXT, version_code TEXT,
    contenu TEXT NOT NULL,
    hash_precedent TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_registre_ticker ON registre(ticker, horodatage);
CREATE INDEX IF NOT EXISTS idx_registre_type ON registre(type, horodatage);
CREATE TRIGGER IF NOT EXISTS registre_sans_modification BEFORE UPDATE ON registre
BEGIN SELECT RAISE(ABORT, 'registre en ajout seul : modification interdite'); END;
CREATE TRIGGER IF NOT EXISTS registre_sans_suppression BEFORE DELETE ON registre
BEGIN SELECT RAISE(ABORT, 'registre en ajout seul : suppression interdite'); END;
CREATE TRIGGER IF NOT EXISTS registre_chaine BEFORE INSERT ON registre
WHEN NEW.hash_precedent != COALESCE((SELECT hash FROM registre ORDER BY id DESC LIMIT 1), '{GENESE}')
BEGIN SELECT RAISE(ABORT, 'registre : la ligne ne prolonge pas la chaîne'); END;
"""


def _canon(valeur) -> str:
    return json.dumps(valeur, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def empreinte_ligne(ligne: dict) -> str:
    """sha256 du JSON canonique des colonnes (hash_precedent compris)."""
    return hashlib.sha256(_canon({c: ligne.get(c) for c in COLONNES}).encode("utf-8")).hexdigest()


def _normaliser(champs: dict) -> dict:
    """Types tels que SQLite les relira (sinon l'empreinte recalculée diffère)."""
    inconnus = set(champs) - set(CHAMPS)
    if inconnus:
        raise ValueError(f"champs inconnus : {sorted(inconnus)}")
    out = {}
    for c, v in champs.items():
        if v is not None and c in _ENTIERS:
            v = int(v)
        elif v is not None and c in _REELS:
            v = nombre_ou_none(v)  # R2c : NaN/infini → None (SQLite relirait NULL : empreinte fausse)
        out[c] = v
    return out
