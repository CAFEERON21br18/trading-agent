"""
utils/real_devise.py — Devise des montants du portefeuille RÉEL (D1, 14/10/2026).

Les montants d'une position réelle (prix, montant investi, P&L, valeur) sont dans
la devise de cotation de l'actif : colonne real_investments.devise, ajoutée sur la
tour par la migration D1 avec 'USD' par défaut (constat du 08/10 sur les
8 positions). Le capital total réel (real_budget) et les budgets des plans sont
en euros. Les montants d'une position ne sont jamais convertis ; seule une
comparaison avec des euros passe par une conversion.
Sur une base neuve, initialiser_real_db ne crée pas cette colonne (le script de
migration, retiré, reste dans l'histoire git) : DEVISE_DEFAUT s'applique alors.
"""

DEVISE_DEFAUT = "USD"
SYMBOLES = {"USD": "$", "EUR": "€"}


def devise_de(position: dict) -> str:
    """Devise d'une position réelle ; DEVISE_DEFAUT si la colonne manque ou est vide."""
    return (position.get("devise") or DEVISE_DEFAUT).upper()


def symbole(devise: str | None) -> str:
    """« USD » → « $ », « EUR » → « € », autre code tel quel ; DEVISE_DEFAUT si vide."""
    d = (devise or DEVISE_DEFAUT).upper()
    return SYMBOLES.get(d, d)


def devise_commune(positions: list[dict]) -> str | None:
    """Devise partagée par toutes les positions, None si elles en ont plusieurs.
    Sans position : DEVISE_DEFAUT (les sommes valent alors 0)."""
    devises = {devise_de(p) for p in positions}
    if not devises:
        return DEVISE_DEFAUT
    return devises.pop() if len(devises) == 1 else None
