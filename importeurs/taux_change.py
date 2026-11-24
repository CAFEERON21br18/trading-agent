"""Clôture quotidienne EURUSD vers la table change du grand livre (dollars pour un euro).

Source par défaut : yfinance, ticker « EURUSD=X », barres d'un jour. Un jour déjà présent dans
la table n'est jamais réécrit : relancer n'ajoute aucun doublon. Le jour en cours (UTC) est
écarté, sa barre n'étant pas encore une clôture ; une valeur absente, nulle ou négative aussi.
Les taux sont arrondis à 6 décimales.

Outil manuel (scripts/ledger_taux.py) : aucun cycle planifié ne remplit la table. Sans taux
stocké dans les 7 jours qui précèdent une clôture, mesures.en_devise lève TauxManquant.
"""
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ledger import ecriture, lecture

TICKER = "EURUSD=X"
SOURCE = "yfinance EURUSD=X"
PRECISION = Decimal("0.000001")
DELAI_S = 20


class SourceIndisponible(RuntimeError):
    """Le cours n'a pas pu être récupéré : rien n'est écrit."""


@dataclass
class Rapport:
    ajoutes: int = 0
    deja_presents: int = 0
    ecartes: list[tuple[date, str]] = field(default_factory=list)  # (jour, raison)
    premier: date | None = None   # premier et dernier jour ajoutés
    dernier: date | None = None


def cloture_yfinance(debut: date, fin: date) -> list[tuple[date, float]]:
    """Clôtures quotidiennes EURUSD=X de debut à fin inclus. Seule fonction qui va en ligne."""
    try:
        import yfinance as yf
        barres = yf.Ticker(TICKER).history(
            start=debut.isoformat(), end=(fin + timedelta(days=1)).isoformat(),
            interval="1d", timeout=DELAI_S)
    except Exception as exc:
        raise SourceIndisponible(f"cours {TICKER} indisponible : {str(exc)[:120]}") from exc
    if barres is None or barres.empty or "Close" not in barres:
        raise SourceIndisponible(f"aucune barre {TICKER} entre {debut} et {fin}")
    return [(horodatage.date(), float(valeur)) for horodatage, valeur in barres["Close"].items()]


def periode_par_defaut(conn, aujourd_hui: date) -> tuple[date, date]:
    """De 7 jours avant le dernier taux stocké (365 jours en arrière sans taux) jusqu'à hier."""
    stockes = lecture.taux_eurusd(conn)
    debut = max(stockes) - timedelta(days=7) if stockes else aujourd_hui - timedelta(days=365)
    return debut, aujourd_hui - timedelta(days=1)


def importer(conn, debut: date, fin: date, telecharger=cloture_yfinance,
             aujourd_hui: date | None = None, appliquer: bool = True) -> Rapport:
    """Inscrit les clôtures EURUSD des jours absents de la table change.

    telecharger(debut, fin) rend des couples (jour, taux) ; les tests passent une source simulée.
    À blanc (appliquer=False), la transaction est annulée : le rapport dit ce qui serait fait.
    """
    aujourd_hui = aujourd_hui or datetime.now(timezone.utc).date()
    cours = dict(telecharger(debut, fin))  # un jour cité deux fois par la source : le dernier
    presents = set(lecture.taux_eurusd(conn))
    rapport = Rapport()
    try:
        for jour in sorted(cours):
            valeur = cours[jour]
            if jour < debut or jour > fin:
                continue
            if jour >= aujourd_hui:
                rapport.ecartes.append((jour, "journée non terminée"))
            elif not isinstance(valeur, (int, float)) or not math.isfinite(valeur) or valeur <= 0:
                rapport.ecartes.append((jour, f"valeur invalide : {valeur!r}"))
            elif jour in presents:
                rapport.deja_presents += 1
            else:
                ecriture.enregistrer_taux(
                    conn, jour, Decimal(str(valeur)).quantize(PRECISION), SOURCE)
                rapport.ajoutes += 1
                rapport.premier = rapport.premier or jour
                rapport.dernier = jour
        if appliquer:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    return rapport
