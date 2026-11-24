"""Clôtures quotidiennes des instruments du grand livre (table cours).

Pour chaque instrument qui a un trade actif : clôtures yfinance, du jour de son premier trade
jusqu'à la veille. Le jour en cours n'est jamais enregistré : sa barre n'est pas une clôture.
Un symbole introuvable chez Yahoo est listé dans le rapport et n'empêche pas les autres.
Relancer n'ajoute aucun doublon : un jour déjà présent avec la même clôture n'est pas réécrit ;
une clôture différente ajoute une ligne, et la dernière saisie l'emporte à la lecture.
Le symbole du grand livre est demandé tel quel à Yahoo, et la clôture est enregistrée dans la
devise de l'instrument. Outil manuel : aucune tâche planifiée, aucun cycle.
"""
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ledger import ecriture, lecture

SOURCE = "yfinance"
DELAI_S = 20
PRECISION = Decimal("0.00000001")  # 8 décimales : au-delà, bruit des flottants de yfinance
RECOUVREMENT_JOURS = 7  # jours déjà stockés redemandés, pour reprendre une clôture corrigée


class SymboleIntrouvable(LookupError):
    """Yahoo ne rend aucune barre pour ce symbole sur la période."""


@dataclass
class Rapport:
    instruments: int = 0  # instruments du grand livre qui ont un trade actif
    ajoutes: int = 0
    deja_presents: int = 0
    ecartes: int = 0  # valeurs invalides rendues par la source
    a_jour: list[str] = field(default_factory=list)  # rien à demander : premier trade aujourd'hui
    introuvables: list[tuple[str, str]] = field(default_factory=list)  # (symbole, raison)


def cloture_yfinance(symbole: str, debut: date, fin: date) -> list[tuple[date, float]]:
    """Clôtures quotidiennes non ajustées du symbole, de debut à fin inclus. Seule fonction qui
    va en ligne."""
    try:
        import yfinance as yf
        barres = yf.Ticker(symbole).history(
            start=debut.isoformat(), end=(fin + timedelta(days=1)).isoformat(),
            interval="1d", auto_adjust=False, timeout=DELAI_S)
    except Exception as exc:
        raise SymboleIntrouvable(f"cours indisponible : {str(exc)[:120]}") from exc
    if barres is None or barres.empty or "Close" not in barres:
        raise SymboleIntrouvable(f"aucune barre entre {debut} et {fin}")
    return [(horodatage.date(), float(valeur)) for horodatage, valeur in barres["Close"].items()]


def periode(premier_trade: date, stockes: list[date], aujourd_hui: date) -> tuple[date, date]:
    """Jours à demander pour un instrument : tout depuis son premier trade s'il manque le début,
    sinon les 7 derniers jours stockés et la suite, jusqu'à la veille."""
    fin = aujourd_hui - timedelta(days=1)
    if not stockes or premier_trade < min(stockes):
        return premier_trade, fin
    return max(premier_trade, max(stockes) - timedelta(days=RECOUVREMENT_JOURS)), fin


def importer(conn, telecharger=cloture_yfinance, aujourd_hui: date | None = None,
             appliquer: bool = True) -> Rapport:
    """Inscrit les clôtures manquantes de chaque instrument négocié.

    telecharger(symbole, debut, fin) rend des couples (jour, clôture) ou lève SymboleIntrouvable ;
    les tests passent une source simulée. À blanc (appliquer=False), la transaction est annulée :
    le rapport dit ce qui serait fait.
    """
    aujourd_hui = aujourd_hui or datetime.now(timezone.utc).date()
    stockes: dict[str, dict[date, Decimal]] = {}
    for c in lecture.cours(conn):
        stockes.setdefault(c.symbole, {})[c.jour] = c.cloture
    rapport = Rapport()
    try:
        for instrument_id, symbole, devise, premier in lecture.instruments_negocies(conn):
            rapport.instruments += 1
            connus = stockes.get(symbole, {})
            debut, fin = periode(premier, list(connus), aujourd_hui)
            if debut > fin:
                rapport.a_jour.append(symbole)
                continue
            try:
                barres = dict(telecharger(symbole, debut, fin))  # un jour cité deux fois : le dernier
            except SymboleIntrouvable as exc:
                rapport.introuvables.append((symbole, str(exc)))
                continue
            for jour in sorted(barres):
                valeur = barres[jour]
                if jour < debut or jour > fin or jour >= aujourd_hui:
                    continue
                if not isinstance(valeur, (int, float)) or not math.isfinite(valeur) or valeur <= 0:
                    rapport.ecartes += 1
                    continue
                cloture = Decimal(str(valeur)).quantize(PRECISION)
                if cloture <= 0:
                    rapport.ecartes += 1
                elif ecriture.enregistrer_cours(conn, instrument_id=instrument_id, jour=jour,
                                                cloture=cloture, devise=devise, source=SOURCE) is None:
                    rapport.deja_presents += 1
                else:
                    rapport.ajoutes += 1
        if appliquer:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    return rapport
