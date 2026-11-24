"""Objets partagés par les mesures. Aucun accès à la base ici."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

MIN_TRADES = 100  # seuil fixé par Lucia le 22 novembre 2026


@dataclass(frozen=True)
class TradeClos:
    """Un aller-retour terminé : une entrée appariée à une sortie."""
    compte_id: int
    symbole: str
    sens: str  # 'long' ou 'court'
    quantite: Decimal
    prix_entree: Decimal
    prix_sortie: Decimal
    ouvert_le: datetime
    clos_le: datetime
    devise: str
    pnl_brut: Decimal
    couts: Decimal
    risque: Decimal | None = None  # perte prévue au stop initial, si connu
    bras: str | None = None

    @property
    def pnl_net(self) -> Decimal:
        return self.pnl_brut - self.couts

    @property
    def r(self) -> Decimal | None:
        """Résultat net exprimé en multiples du risque initial."""
        if self.risque is None or self.risque == 0:
            return None
        return self.pnl_net / self.risque


@dataclass(frozen=True)
class PositionOuverte:
    """Un lot encore ouvert après appariement."""
    compte_id: int
    symbole: str
    sens: str
    quantite: Decimal
    prix_entree: Decimal
    ouvert_le: datetime
    devise: str
    couts: Decimal = Decimal("0")  # frais d'entrée de la quantité encore ouverte


@dataclass(frozen=True)
class Mesure:
    """Une valeur calculée, avec ce qu'il faut pour savoir si elle prouve quelque chose."""
    nom: str
    valeur: float | None
    n: int
    debut: date | None
    fin: date | None
    decidable: bool
    raison: str = ""


def mesure(nom: str, valeur, n: int, debut=None, fin=None) -> Mesure:
    """Construit une Mesure et décide si elle est décidable."""
    if valeur is None:
        return Mesure(nom, None, n, debut, fin, False, "non calculable")
    if n < MIN_TRADES:
        return Mesure(nom, float(valeur), n, debut, fin, False,
                      f"{n} trades sur {MIN_TRADES} requis")
    return Mesure(nom, float(valeur), n, debut, fin, True)
