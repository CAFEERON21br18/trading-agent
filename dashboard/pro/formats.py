"""
dashboard/pro/formats.py — Mise en forme des chiffres du dashboard professionnel.

Un gain ou une perte porte toujours son signe, « + » ou « − » : la couleur ne fait que le
répéter. Une valeur absente s'écrit « — », jamais 0. Écriture française : virgule décimale,
espace insécable entre les milliers et avant l'unité.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

ABSENT = "—"
MOINS = "−"  # signe moins typographique (U+2212), distinct du tiret de « — »
ESPACE = " "
SYMBOLES = {"EUR": "€", "USD": "$"}


def _decimal(valeur) -> Decimal:
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))


def nombre(valeur, decimales: int = 2) -> str:
    """Valeur absolue arrondie, écrite à la française : 1 234,50."""
    arrondi = abs(_decimal(valeur)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    entier, _, fraction = f"{arrondi:f}".partition(".")
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    entier = ESPACE.join([entier] + groupes)
    return f"{entier},{fraction}" if fraction else entier


def _signe(valeur, decimales: int) -> str:
    """« + », « − » ou rien, d'après la valeur telle qu'elle sera affichée (un −0,001 s'écrit 0,00)."""
    arrondi = _decimal(valeur).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return "+" if arrondi > 0 else MOINS if arrondi < 0 else ""


def montant(valeur, devise: str) -> str:
    """Montant sans signe (un prix, des frais) : 12,30 €. None : « — »."""
    if valeur is None:
        return ABSENT
    negatif = MOINS if _signe(valeur, 2) == MOINS else ""
    return f"{negatif}{nombre(valeur)}{ESPACE}{SYMBOLES.get(devise, devise)}"


def montant_signe(valeur, devise: str) -> str:
    """Gain ou perte, avec son signe : +12,30 € ou −5,00 €. None : « — »."""
    if valeur is None:
        return ABSENT
    return f"{_signe(valeur, 2)}{nombre(valeur)}{ESPACE}{SYMBOLES.get(devise, devise)}"


def pourcent(valeur, decimales: int = 1) -> str:
    """Part entre 0 et 1, écrite en pourcentage : 0,5 donne 50,0 %."""
    if valeur is None:
        return ABSENT
    cent = _decimal(valeur) * 100
    negatif = MOINS if _signe(cent, decimales) == MOINS else ""
    return f"{negatif}{nombre(cent, decimales)}{ESPACE}%"


def en_r(valeur) -> str:
    """Résultat en multiples du risque initial : +2,00 R. None (stop inconnu) : « — »."""
    if valeur is None:
        return ABSENT
    return f"{_signe(valeur, 2)}{nombre(valeur)}{ESPACE}R"


def quantite(valeur) -> str:
    """Quantité de titres, jusqu'à 6 décimales, sans zéros de fin."""
    if valeur is None:
        return ABSENT
    texte = nombre(valeur, 6)
    return texte.rstrip("0").rstrip(",") if "," in texte else texte


def jour(valeur) -> str:
    """Date au format jj/mm/aaaa (jour UTC pour un horodatage)."""
    if valeur is None:
        return ABSENT
    if isinstance(valeur, datetime):
        valeur = valeur.date()
    return valeur.strftime("%d/%m/%Y") if isinstance(valeur, date) else str(valeur)


def classe(valeur) -> str:
    """Couleur qui accompagne le signe (jamais seule) : vert, rouge, ou rien."""
    if valeur is None:
        return ""
    signe = _signe(valeur, 2)
    return "text-emerald-400" if signe == "+" else "text-red-400" if signe == MOINS else ""
