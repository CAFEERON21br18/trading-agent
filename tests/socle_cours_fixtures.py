"""
tests/socle_cours_fixtures.py — Source de cours simulée pour les tests des clôtures quotidiennes
(importeurs/cours.py, scripts/ledger_cours.py, bouton « Synchroniser »). Cours inventés, aucun réseau.
"""

from datetime import date

from importeurs import cours as ic

AUJOURD_HUI = date(2030, 1, 10)


def j(jour: int) -> date:
    return date(2030, 1, jour)


def source(par_symbole: dict):
    """Source simulée : rend les barres du symbole, ou le dit introuvable ; note chaque demande."""
    appels = []

    def telecharger(symbole, debut, fin):
        appels.append((symbole, debut, fin))
        if symbole not in par_symbole:
            raise ic.SymboleIntrouvable(f"aucune barre entre {debut} et {fin}")
        return list(par_symbole[symbole])
    telecharger.appels = appels
    return telecharger
