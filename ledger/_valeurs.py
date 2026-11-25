"""Contrôles de valeurs partagés par les écritures du grand livre (sortis de ecriture.py)."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


class EcritureInvalide(ValueError):
    """Valeur refusée avant d'atteindre le grand livre."""


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positif(valeur, nom: str) -> str:
    try:
        d = Decimal(str(valeur))
    except InvalidOperation as exc:
        raise EcritureInvalide(f"{nom} illisible : {valeur!r}") from exc
    if not d.is_finite() or d <= 0:
        raise EcritureInvalide(f"{nom} doit être strictement positif : {valeur!r}")
    return str(d)


def _fini(valeur, nom: str) -> str:
    """Nombre fini, de signe quelconque : la valeur d'un compte peut être nulle ou négative."""
    try:
        d = Decimal(str(valeur))
    except InvalidOperation as exc:
        raise EcritureInvalide(f"{nom} illisible : {valeur!r}") from exc
    if not d.is_finite():
        raise EcritureInvalide(f"{nom} doit être un nombre fini : {valeur!r}")
    return str(d)


def _iso(horodatage: datetime) -> str:
    if horodatage.tzinfo is None:
        horodatage = horodatage.replace(tzinfo=timezone.utc)
    return horodatage.astimezone(timezone.utc).isoformat()
