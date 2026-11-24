"""Écriture des cours de clôture. Partie de ledger/ecriture.py, sortie pour la règle des 200 lignes :
ecriture.py la ré-exporte, on l'appelle par ecriture.enregistrer_cours."""
from datetime import date
from decimal import Decimal

from ._valeurs import _maintenant, _positif


def enregistrer_cours(conn, *, instrument_id: int, jour: date, cloture, devise: str, source: str):
    """Ajoute la clôture d'un instrument pour un jour. Renvoie son id, ou None si la dernière
    saisie de ce jour porte déjà la même clôture.

    Une clôture différente pour un jour déjà présent ajoute une ligne : à la lecture, la
    dernière saisie l'emporte. Rien n'est jamais modifié ni effacé.
    """
    valeur = _positif(cloture, "clôture")
    derniere = conn.execute(
        "SELECT cloture FROM cours WHERE instrument_id = ? AND jour = ? ORDER BY id DESC LIMIT 1",
        (instrument_id, jour.isoformat()),
    ).fetchone()
    if derniere is not None and Decimal(derniere["cloture"]) == Decimal(valeur):
        return None
    cur = conn.execute(
        "INSERT INTO cours (instrument_id, jour, cloture, devise, source, saisi_le)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (instrument_id, jour.isoformat(), valeur, devise.upper(), source, _maintenant()),
    )
    return cur.lastrowid
