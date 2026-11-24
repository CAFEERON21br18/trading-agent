"""
rejeu/reference.py — « Acheter et garder » : la référence à laquelle le rejeu est comparé.

Même univers, à parts égales, mêmes frais, même capital que la stratégie. Calcul pur sur les
barres : ni agent, ni base. Deux références :
- ANNUELLE : chaque année, la valeur du compte est répartie à parts égales entre les titres qui
  cotent dans la première semaine de l'année ; chacun est acheté à l'ouverture de sa première
  barre de l'année et vendu à la clôture de sa dernière. Un titre coté en cours d'année attend
  l'année suivante. La valeur est réinvestie d'une année sur l'autre ;
- PÉRIODE : le capital est partagé en autant de parts égales que de titres ; chaque part est
  investie à l'ouverture de la première barre du titre depuis le 01/01/2018 (un titre coté plus
  tard entre à sa première barre ; sa part attend en espèces) et gardée jusqu'à la clôture de sa
  dernière barre de la période (31/12/2025).
Les frais sont payés sur la part : on n'achète que ce qu'elle permet, frais compris. Une part
trop petite pour payer les frais reste en espèces.
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal

from rejeu import frais
from rejeu import parametres as P
from rejeu.resultat import REFERENCE_ANNUELLE, REFERENCE_PERIODE, Ordre, Resultat

SEMAINE = 7  # un titre est « là en début d'année » s'il cote dans les 7 premiers jours


def _instant(jour: date, heure: int) -> datetime:
    return datetime.combine(jour, time(heure), tzinfo=timezone.utc)


class _Portefeuille:
    """Espèces et lignes d'un compte « acheter et garder »."""

    def __init__(self, nature: str, capital: int, profil: str):
        self.res, self.profil = Resultat(nature, capital, profil), profil
        self.especes, self.lignes, self.cours = Decimal(capital), {}, {}

    def acheter(self, ticker: str, part: Decimal, prix: float, jour: date, ref: str) -> None:
        taux = P.PROFILS[self.profil]["ecart"].get(frais.type_titre(ticker), Decimal(0)) if P.PROFILS[self.profil]["ecart"] else Decimal(0)
        montant = (part - P.PROFILS[self.profil]["par_ordre"]) / (1 + taux)  # ce que la part achète, frais payés
        if montant <= 0:
            return  # part trop petite : elle reste en espèces
        quantite = float(montant / frais.decimal(prix))
        couts = frais.entree(self.profil, ticker, quantite, prix)
        self.especes -= frais.decimal(quantite) * frais.decimal(prix) + frais.total(couts)
        self.lignes[ticker] = (quantite, prix, jour)
        self.res.ordres.append(Ordre(f"{ref}-achat", ticker, _instant(jour, 8), "achat", quantite, prix, tuple(couts)))

    def vendre(self, ticker: str, prix: float, jour: date, ref: str, statut: str) -> None:
        quantite, prix_entree, jour_entree = self.lignes.pop(ticker)
        couts = frais.sortie(self.profil, ticker, quantite, prix, prix_entree, jour_entree, jour)
        self.especes += frais.decimal(quantite) * frais.decimal(prix) - frais.total(couts)
        self.res.ordres.append(Ordre(f"{ref}-vente", ticker, _instant(jour, 22), "vente", quantite, prix,
                                     tuple(couts), statut=statut))

    def valeur(self, jour: date) -> Decimal:
        total = self.especes
        for ticker, (quantite, prix_entree, jour_entree) in self.lignes.items():
            total += frais.decimal(quantite) * frais.decimal(self.cours.get(ticker, prix_entree))
            total -= frais.financement(self.profil, quantite * prix_entree, jour_entree, jour)
        return total


def _calendrier(barres: dict, debut: date, fin: date | None) -> list[date]:
    return sorted({j for df in barres.values() for j in df.index if j >= debut and (fin is None or j <= fin)})


def annuelle(capital: int, profil: str, barres: dict, fin: date | None = None) -> Resultat:
    """Référence rachetée chaque année, de 2018 à la dernière barre (ou `fin`)."""
    pf = _Portefeuille(REFERENCE_ANNUELLE, capital, profil)
    lignes = {t: df.to_dict("index") for t, df in barres.items()}
    calendrier = _calendrier(barres, P.DEBUT_REJEU, fin)
    for annee in sorted({j.year for j in calendrier}):
        jours = [j for j in calendrier if j.year == annee]
        du_titre = {t: [j for j in jours if j in lignes[t]] for t in barres}
        inclus = [t for t in barres if du_titre[t] and (du_titre[t][0] - date(annee, 1, 1)).days < SEMAINE]
        part = pf.valeur(jours[0]) / len(inclus) if inclus else Decimal(0)
        for jour in jours:
            for t in inclus:
                if jour == du_titre[t][0]:
                    pf.acheter(t, part, lignes[t][jour]["Open"], jour, f"{annee}-{t}")
            for t in barres:
                if jour in lignes[t]:
                    pf.cours[t] = lignes[t][jour]["Close"]
            for t in inclus:
                if jour == du_titre[t][-1] and t in pf.lignes:
                    pf.vendre(t, lignes[t][jour]["Close"], jour, f"{annee}-{t}", "FIN_ANNEE")
            pf.res.valeurs.append((jour, pf.valeur(jour)))
    return pf.res


def periode(capital: int, profil: str, barres: dict, fin: date = P.FIN_PERIODE) -> Resultat:
    """Référence achetée une fois et gardée jusqu'à la fin de la période."""
    pf = _Portefeuille(REFERENCE_PERIODE, capital, profil)
    lignes = {t: df.to_dict("index") for t, df in barres.items()}
    calendrier = _calendrier(barres, P.DEBUT_REJEU, fin)
    du_titre = {t: [j for j in calendrier if j in lignes[t]] for t in barres}
    part = Decimal(capital) / len(barres) if barres else Decimal(0)
    for jour in calendrier:
        for t in barres:
            if du_titre[t] and jour == du_titre[t][0]:
                pf.acheter(t, part, lignes[t][jour]["Open"], jour, f"periode-{t}")
            if jour in lignes[t]:
                pf.cours[t] = lignes[t][jour]["Close"]
        for t in barres:
            if du_titre[t] and jour == du_titre[t][-1] and t in pf.lignes:
                pf.vendre(t, lignes[t][jour]["Close"], jour, f"periode-{t}", "FIN_PERIODE")
        pf.res.valeurs.append((jour, pf.valeur(jour)))
    return pf.res
