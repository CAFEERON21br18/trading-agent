"""
rejeu/texte.py — Mise en forme des chiffres du rapport du rejeu (et de sa page).

Écriture française ; un gain ou une perte porte son signe ; une valeur non calculable s'écrit
« — », jamais 0. Calcul pur.
"""

ABSENT = "—"
MOINS = "−"
ESPACE = " "


def nombre(valeur: float, decimales: int = 2) -> str:
    """Valeur absolue, à la française : 1 234,50."""
    entier, _, fraction = f"{abs(valeur):.{decimales}f}".partition(".")
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    entier = ESPACE.join([entier] + groupes)
    return f"{entier},{fraction}" if fraction else entier


def _signe(valeur: float, decimales: int) -> str:
    arrondi = round(valeur, decimales)
    return "+" if arrondi > 0 else MOINS if arrondi < 0 else ""


def eur(valeur, decimales: int = 2) -> str:
    """Gain ou perte en euros, signé."""
    return ABSENT if valeur is None else f"{_signe(valeur, decimales)}{nombre(valeur, decimales)}{ESPACE}€"


def montant(valeur, decimales: int = 2) -> str:
    """Montant en euros, sans signe (frais, valeur d'un compte)."""
    if valeur is None:
        return ABSENT
    return f"{MOINS if round(valeur, decimales) < 0 else ''}{nombre(valeur, decimales)}{ESPACE}€"


def pct(valeur, decimales: int = 1, signe: bool = True) -> str:
    """Part (0,5 = 50 %), signée par défaut."""
    if valeur is None:
        return ABSENT
    cent = valeur * 100
    prefixe = _signe(cent, decimales) if signe else (MOINS if round(cent, decimales) < 0 else "")
    return f"{prefixe}{nombre(cent, decimales)}{ESPACE}%"


def ratio(valeur, decimales: int = 2) -> str:
    return ABSENT if valeur is None else f"{_signe(valeur, decimales)}{nombre(valeur, decimales)}"


def intervalle(bornes) -> str:
    return ABSENT if not bornes else f"{eur(bornes[0])} à {eur(bornes[1])}"


def oui_non(vraie: bool) -> str:
    return "vraie" if vraie else "fausse"


def tableau(entetes: list[str], lignes: list[list[str]]) -> str:
    """Tableau Markdown."""
    sortie = ["| " + " | ".join(entetes) + " |", "|" + "|".join("---" for _ in entetes) + "|"]
    sortie += ["| " + " | ".join(str(c) for c in ligne) + " |" for ligne in lignes]
    return "\n".join(sortie)
