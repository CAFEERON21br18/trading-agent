"""
scripts/_banc_fichiers.py — Fichiers du banc de rejeu du chat : cas, résultats, logs.

Tout reste dans data/chat_cas/ (ignoré par git : prompts et réponses contiennent
le portefeuille réel) :
- <audit_id>.json et m_<horodatage>.json : un cas par fichier, jamais réécrit ;
- resultats/<horodatage>_<mode>.json : sorties de scripts/rejouer_chat.py ;
- tmp/ : copie jetable de la base (mode à blanc) ;
- banc.log : logs du banc, à la place de logs/ (production).
"""

import contextlib
import json
import logging
import os
from datetime import datetime, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER_CAS = os.path.join(RACINE, "data", "chat_cas")


def horodatage() -> str:
    """AAAAMMJJ_HHMMSS en UTC (noms de fichiers)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ecrire_exclusif(chemin: str, donnees: dict) -> bool:
    """Écrit un nouveau fichier JSON ; False s'il existe déjà (jamais réécrit)."""
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    try:
        with open(chemin, "x", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
        return True
    except FileExistsError:
        return False


def lire_json(chemin: str) -> dict:
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def lister_cas(dossier: str = DOSSIER_CAS) -> list[dict]:
    """Cas du dossier (hors resultats/ et tmp/), avec leur identifiant « _id » = nom du fichier."""
    if not os.path.isdir(dossier):
        return []
    cas = []
    for nom in os.listdir(dossier):
        chemin = os.path.join(dossier, nom)
        if nom.endswith(".json") and os.path.isfile(chemin):
            cas.append({**lire_json(chemin), "_id": nom[:-5]})
    # audits par numéro, puis cas manuels par horodatage
    return sorted(cas, key=lambda c: (not c["_id"].isdigit(), int(c["_id"]) if c["_id"].isdigit() else 0, c["_id"]))


def ecrire_resultats(dossier: str, mode: str, contenu: dict) -> str:
    """resultats/<horodatage>_<mode>.json (suffixe ajouté si le nom existe déjà)."""
    base = os.path.join(dossier, "resultats", f"{horodatage()}_{mode}")
    chemin, n = f"{base}.json", 2
    while not ecrire_exclusif(chemin, contenu):
        chemin, n = f"{base}_{n}.json", n + 1
    return chemin


def _loggers() -> list[logging.Logger]:
    return [logging.getLogger()] + [l for l in logging.Logger.manager.loggerDict.values()
                                    if isinstance(l, logging.Logger)]


@contextlib.contextmanager
def journaux_detaches(dossier: str = DOSSIER_CAS):
    """Le temps du bloc, les logs de production (logs/alphasignal.log, logs/errors.log) vont
    dans <dossier>/banc.log, y compris ceux des loggers créés pendant le bloc (imports tardifs :
    utils.logger lit LOG_FILE_MAIN et LOG_FILE_ERROR à chaque get_logger)."""
    from utils import logger as journal
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.abspath(os.path.join(dossier, "banc.log"))
    prod = {os.path.normcase(os.path.abspath(p)) for p in (journal.LOG_FILE_MAIN, journal.LOG_FILE_ERROR)}
    remplacant = logging.FileHandler(chemin, encoding="utf-8")
    remplacant.setFormatter(logging.Formatter(journal.LOG_FORMAT, datefmt=journal.DATE_FORMAT))
    retires = []
    for lg in _loggers():
        prod_lg = [h for h in lg.handlers if isinstance(h, logging.FileHandler)
                   and os.path.normcase(h.baseFilename) in prod]
        for h in prod_lg:
            lg.removeHandler(h)
            retires.append((lg, h))
        if prod_lg:
            lg.addHandler(remplacant)
    try:
        with mock.patch.object(journal, "LOG_FILE_MAIN", chemin), \
             mock.patch.object(journal, "LOG_FILE_ERROR", chemin):
            yield chemin
    finally:
        for lg in _loggers():  # remplaçant et handlers créés pendant le bloc vers banc.log
            for h in [h for h in lg.handlers if isinstance(h, logging.FileHandler)
                      and os.path.normcase(h.baseFilename) == os.path.normcase(chemin)]:
                lg.removeHandler(h)
                h.close()
        for lg, h in retires:
            lg.addHandler(h)
        remplacant.close()
