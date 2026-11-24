"""
dashboard/pro/latent.py — Résultat latent des positions ouvertes d'un compte.

Module pur (ni Flask, ni réseau, ni écriture). Chaque position est valorisée au dernier prix
connu (prix.py : le cours du grand livre, sinon celui de la base de l'agent). Si le prix manque,
date de plus de 3 jours de bourse ou n'est pas dans la devise de la position, celle-ci est
marquée « prix indisponible » et exclue du total : elle n'est jamais comptée à 0.
Sans aucune position valorisée, le total est None. Un taux de change manquant pour la bascule
donne « taux indisponible » au lieu d'un total.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import mesures
from dashboard.pro import donnees, prix as prix_agent

PRIX_INDISPONIBLE = "prix indisponible"


@dataclass(frozen=True)
class LigneLatente:
    position: object  # mesures.PositionOuverte
    prix: prix_agent.Prix | None  # dernier prix utilisable, sinon None
    latent: Decimal | None  # dans la devise de cotation de la position
    indisponible: str = ""


@dataclass(frozen=True)
class Latent:
    lignes: list
    total: Decimal | None  # dans la devise d'affichage ; None si rien n'a pu être valorisé
    indisponible: str = ""  # « taux indisponible » : le total n'a pas pu être basculé

    @property
    def valorisees(self) -> int:
        return sum(1 for l in self.lignes if l.latent is not None)

    @property
    def sans_prix(self) -> int:
        return len(self.lignes) - self.valorisees

    @property
    def jours_des_cours(self) -> tuple[date, date] | None:
        """(plus ancien, plus récent) jour des cours utilisés, ou None si rien n'est valorisé."""
        jours = [l.prix.jour for l in self.lignes if l.latent is not None]
        return (min(jours), max(jours)) if jours else None


def resultat_latent(source: donnees.Source, devise: str, prix: dict, aujourd_hui: date,
                    periode: str = "tout") -> Latent:
    """Valorise chaque position ouverte du compte et additionne celles qui ont un prix.

    prix : symbole -> prix.Prix (prix.derniers_prix). aujourd_hui : jour de la lecture, qui sert
    à l'âge du prix et au taux de la bascule (dernier taux connu sur 7 jours).
    """
    if devise not in donnees.DEVISES:
        raise ValueError(f"devise d'affichage inconnue : {devise!r}")
    lignes, total, sans_taux, valorisees = [], Decimal("0"), False, []
    for p in donnees.positions_ouvertes(source, periode):
        connu = prix.get(p.symbole)
        if connu is not None and connu.devise not in (None, p.devise):
            connu = None  # cours enregistré dans une autre devise que la position : inutilisable
        if not prix_agent.utilisable(connu, aujourd_hui):
            lignes.append(LigneLatente(p, None, None, PRIX_INDISPONIBLE))
            continue
        ecart = connu.valeur - p.prix_entree if p.sens == "long" else p.prix_entree - connu.valeur
        latent = ecart * p.quantite
        lignes.append(LigneLatente(p, connu, latent))
        valorisees.append(p.devise)
        if p.devise not in donnees.DEVISES:
            continue  # devise ni euro ni dollar : dite plus bas, jamais convertie au hasard
        try:
            total += mesures.convertir(latent, p.devise, devise, aujourd_hui, source.taux)
        except mesures.TauxManquant:
            sans_taux = True
    if donnees.raison_devise(valorisees):
        return Latent(lignes, None, donnees.raison_devise(valorisees))
    if sans_taux:
        return Latent(lignes, None, donnees.TAUX_INDISPONIBLE)
    return Latent(lignes, total if valorisees else None)
