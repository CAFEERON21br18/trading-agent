"""
dashboard/pro/donnees.py — Préparation des données des pages du dashboard professionnel.

Module pur : ni Flask, ni réseau, ni écriture. Une fonction par bloc d'affichage, toujours
pour UN compte et UNE devise d'affichage (EUR ou USD). Les comptes ne sont jamais additionnés
entre eux : argent réel et argent fictif ne se mélangent pas, et charger() exige un compte.
Un taux de change manquant (mesures.TauxManquant) donne un bloc « taux indisponible » au lieu
d'un chiffre, comme une devise autre que l'euro et le dollar (« devise non convertie »).
Le résultat latent des positions ouvertes est dans latent.py.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import ledger
import mesures

DEVISES = ("EUR", "USD")
TAUX_INDISPONIBLE = "taux indisponible"

# Date d'effet du correctif du prix d'entrée paper (version 2 du mécanisme d'entrée).
# Référence : docs/REGISTRE_CRITERES.md §9.4, « La date effective est l'entry_date de la
# première position paper enregistrée avec la version 2 du mécanisme d'entrée. » Le registre
# donne la règle, pas le jour : valeur lue le 24/11/2026 dans la base de la tour, en lecture
# seule (plus ancienne entry_date des positions où mecanisme_entree = 2 ; aucune position
# d'un autre mécanisme n'est ouverte après elle).
CORRECTIF_PRIX_ENTREE = datetime(2026, 10, 21, 13, 31, 27, tzinfo=timezone.utc)
# Filtre de période du compte paper : clé de l'URL -> première date d'ouverture retenue
PERIODES = {"tout": None, "correctif": CORRECTIF_PRIX_ENTREE}


@dataclass(frozen=True)
class Source:
    """Ce qui est lu une fois dans le grand livre pour un compte, et un seul."""
    compte: ledger.Compte
    executions: list
    mouvements: list
    taux: dict


@dataclass(frozen=True)
class Bloc:
    """Résultat d'un bloc : sa valeur, ou la raison pour laquelle il n'y a pas de chiffre."""
    valeur: object = None
    indisponible: str = ""


@dataclass(frozen=True)
class Frais:
    total: Decimal  # dans la devise d'affichage
    ordres: int  # ordres du compte sur la période
    ordres_avec_frais: int


def charger(conn, compte_id: int) -> Source:
    """Lit les exécutions actives, les mouvements et les taux pour le compte demandé."""
    compte = next((c for c in ledger.comptes(conn) if c.id == compte_id), None)
    if compte is None:
        raise ValueError(f"compte inconnu : {compte_id!r} (un compte, et un seul, est requis)")
    return Source(compte, ledger.executions_actives(conn, compte.id),
                  ledger.mouvements(conn, compte.id), ledger.taux_eurusd(conn))


def _depuis(periode: str):
    if periode not in PERIODES:
        raise ValueError(f"période inconnue : {periode!r}")
    return PERIODES[periode]


def _devise(devise: str) -> str:
    if devise not in DEVISES:
        raise ValueError(f"devise d'affichage inconnue : {devise!r}")
    return devise


def raison_devise(devises) -> str:
    """Message si une devise présente n'est ni l'euro ni le dollar : elle n'est pas convertie."""
    autres = sorted(d for d in set(devises) if d not in DEVISES)
    return f"devise non convertie : {', '.join(autres)}" if autres else ""


def _essayer(devises, devise: str, calcul) -> Bloc:
    """Bloc du calcul, ou la raison pour laquelle la bascule de devise est impossible."""
    _devise(devise)
    raison = raison_devise(devises)
    if raison:
        return Bloc(indisponible=raison)
    try:
        return Bloc(calcul())
    except mesures.TauxManquant:
        return Bloc(indisponible=TAUX_INDISPONIBLE)


def _reconstruits(source: Source, periode: str):
    """(trades clos, positions ouvertes) dont l'entrée date de la période, en devise de cotation."""
    clos, ouvertes = mesures.reconstruire(source.executions)
    depuis = _depuis(periode)
    if depuis is not None:
        clos = [t for t in clos if t.ouvert_le >= depuis]
        ouvertes = [p for p in ouvertes if p.ouvert_le >= depuis]
    return clos, ouvertes


def trades_clos(source: Source, devise: str, periode: str = "tout") -> Bloc:
    """Trades clos exprimés dans la devise d'affichage, triés par date de clôture."""
    clos, _ = _reconstruits(source, periode)
    return _essayer((t.devise for t in clos), devise,
                    lambda: mesures.en_devise(clos, devise, source.taux))


def lignes_trades(source: Source, devise: str, periode: str = "tout") -> list[tuple]:
    """Pour les tableaux : (trade en devise de cotation, le même converti ou None sans taux)."""
    clos, _ = _reconstruits(source, periode)
    return [(t, _essayer([t.devise], devise,
                         lambda t=t: mesures.en_devise([t], devise, source.taux)[0]).valeur)
            for t in clos]


def positions_ouvertes(source: Source, periode: str = "tout") -> list:
    """Positions encore ouvertes, dans la devise de cotation de leur titre."""
    return _reconstruits(source, periode)[1]


def tableau_mesures(source: Source, devise: str, periode: str = "tout") -> Bloc:
    """Les mesures de mesures.tableau, par nom, sur les trades clos de la période."""
    bloc = trades_clos(source, devise, periode)
    if bloc.indisponible:
        return bloc
    return Bloc({m.nom: m for m in mesures.tableau(bloc.valeur)})


def _mesure_mouvements(source: Source, devise: str, calcul, types: tuple) -> Bloc:
    """Seuls les mouvements du calcul sont basculés : un dividende sans taux ne bloque pas les apports."""
    retenus = [m for m in source.mouvements if m.type in types]
    return _essayer((m.devise for m in retenus), devise, lambda: calcul(
        mesures.mouvements_en_devise(retenus, devise, source.taux)))


def dividendes(source: Source, devise: str) -> Bloc:
    return _mesure_mouvements(source, devise, mesures.dividendes, ("dividende",))


def apports_nets(source: Source, devise: str) -> Bloc:
    """Dépôts moins retraits."""
    return _mesure_mouvements(source, devise, mesures.apports_nets, ("depot", "retrait"))


def total_frais(source: Source, devise: str, periode: str = "tout") -> Bloc:
    """Frais payés sur tous les ordres du compte (positions ouvertes comprises), au taux du
    jour de chaque ordre."""
    depuis = _depuis(periode)
    ordres = [e for e in source.executions if depuis is None or e.horodatage >= depuis]
    payants = [e for e in ordres if e.couts > 0]
    return _essayer((e.devise for e in payants), devise, lambda: Frais(
        sum((mesures.convertir(e.couts, e.devise, devise, e.horodatage.date(), source.taux)
             for e in payants), Decimal("0")), len(ordres), len(payants)))


def serie_cumulee(source: Source, devise: str, periode: str = "tout") -> Bloc:
    """Résultat net réalisé cumulé : un point (jour, cumul) par jour de clôture."""
    bloc = trades_clos(source, devise, periode)
    if bloc.indisponible:
        return bloc
    par_jour: dict[date, Decimal] = {}
    for t in bloc.valeur:
        jour = t.clos_le.date()
        par_jour[jour] = par_jour.get(jour, Decimal("0")) + t.pnl_net
    serie, cumul = [], Decimal("0")
    for jour in sorted(par_jour):
        cumul += par_jour[jour]
        serie.append((jour, cumul))
    return Bloc(serie)
