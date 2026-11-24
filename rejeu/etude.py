"""
rejeu/etude.py — Tout ce qui se lit d'une configuration dans le grand livre du rejeu : mesures de
la période, de chaque année, des deux références, verdict.

Lecture seule du grand livre (data/rejeu/ledger_rejeu.db). Sert au rapport ET à la page
/pro/rejeu : les deux affichent donc exactement les mêmes chiffres. N'importe pas l'agent.
"""

from dataclasses import dataclass

import ledger
from rejeu import grand_livre, mesure, verdict
from rejeu import parametres as P
from rejeu.resultat import REFERENCE_ANNUELLE, REFERENCE_PERIODE, STRATEGIE, nom_compte


@dataclass(frozen=True)
class Annee:
    numero: int
    partielle: bool
    strategie: mesure.Bilan
    reference: mesure.Bilan  # référence rachetée chaque année
    ecart: float | None  # rendement de la stratégie moins celui de la référence annuelle


@dataclass(frozen=True)
class Etude:
    capital: int
    profil: str
    decide: bool  # la configuration du critère
    periode: mesure.Bilan
    reference_annuelle: mesure.Bilan
    reference_periode: mesure.Bilan
    ecart_annuelle: float | None
    ecart_periode: float | None
    annees: list  # 2018 … 2025, puis 2026 (partielle) si elle existe
    verdict: str
    conditions: list
    ouvertes: int  # positions encore ouvertes à la dernière barre
    sorties: dict  # motif de sortie -> nombre d'ordres
    courbes: dict  # nature -> [(jour, valeur)]


def configurations(conn) -> list[tuple[int, str]]:
    """(capital, profil) présents dans le grand livre, la configuration qui décide en tête."""
    noms = grand_livre.comptes(conn)
    presentes = [(c, p) for c in P.CAPITAUX for p in P.PROFILS if nom_compte(STRATEGIE, c, p) in noms]
    return sorted(presentes, key=lambda cp: (cp != P.CONFIG_QUI_DECIDE, cp))


def etudier(conn, capital: int, profil: str) -> Etude:
    """Lit les trois comptes de la configuration et calcule ses mesures et son verdict."""
    ids = grand_livre.comptes(conn)
    comptes = {n: ids[nom_compte(n, capital, profil)] for n in (STRATEGIE, REFERENCE_ANNUELLE, REFERENCE_PERIODE)}
    trades = {n: grand_livre.trades(conn, i) for n, i in comptes.items()}
    valeurs = {n: grand_livre.valeurs(conn, i) for n, i in comptes.items()}
    debut, fin = P.DEBUT_REJEU, P.FIN_PERIODE

    def bilan(nature, d, f):
        return mesure.bilan(trades[nature], valeurs[nature], d, f, capital)

    dernier_jour = valeurs[STRATEGIE][-1][0] if valeurs[STRATEGIE] else fin
    numeros = list(P.ANNEES) + ([dernier_jour.year] if dernier_jour.year > P.ANNEES[-1] else [])
    annees = []
    for numero in numeros:
        d, f = mesure.annee(numero, dernier_jour)
        annees.append(Annee(numero, numero not in P.ANNEES, bilan(STRATEGIE, d, f), bilan(REFERENCE_ANNUELLE, d, f),
                            mesure.ecart(valeurs[STRATEGIE], valeurs[REFERENCE_ANNUELLE], d, f, capital)))
    periode, ref_a, ref_p = (bilan(n, debut, fin) for n in (STRATEGIE, REFERENCE_ANNUELLE, REFERENCE_PERIODE))
    rendu, conditions = verdict.rendre(periode, ref_a, ref_p,
                                       {a.numero: a.strategie for a in annees if not a.partielle})
    return Etude(
        capital=capital, profil=profil, decide=(capital, profil) == P.CONFIG_QUI_DECIDE,
        periode=periode, reference_annuelle=ref_a, reference_periode=ref_p,
        ecart_annuelle=mesure.ecart(valeurs[STRATEGIE], valeurs[REFERENCE_ANNUELLE], debut, fin, capital),
        ecart_periode=mesure.ecart(valeurs[STRATEGIE], valeurs[REFERENCE_PERIODE], debut, fin, capital),
        annees=annees, verdict=rendu, conditions=conditions,
        ouvertes=len(grand_livre.positions_ouvertes(conn, comptes[STRATEGIE])),
        sorties=grand_livre.sorties_par_motif(conn, comptes[STRATEGIE]), courbes=valeurs)


def lire(dossier: str | None = None, configs: list | None = None) -> list[Etude]:
    """Études lues dans le grand livre du rejeu, ouvert en lecture seule ; la configuration qui
    décide en tête. Liste vide si le rejeu n'a jamais été lancé."""
    conn = ledger.ouvrir_lecture(grand_livre.chemin(dossier))
    if conn is None:
        return []
    try:
        return [etudier(conn, c, p) for c, p in (configs or configurations(conn))]
    finally:
        conn.close()
