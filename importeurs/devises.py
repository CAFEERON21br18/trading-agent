"""Devise de cotation d'un ticker paper.

Le paper trader traite 1 € = 1 $ et sa table positions n'a pas de devise. Règle retenue pour le
grand livre (décision de Lucia du 24 novembre 2026) : EUR pour un ticker à suffixe de place
européenne (.PA, .DE, .AS, .MI, .MC, .LS), USD sinon. devise_incertaine signale les tickers pour
lesquels ce USD par défaut est douteux, sans changer la règle.
"""

SUFFIXES_EUR = (".PA", ".DE", ".AS", ".MI", ".MC", ".LS")
INDICES_USD = ("^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX")


def devise_cotation(ticker: str) -> str:
    """Devise retenue pour un ticker paper : EUR pour un suffixe de place européenne
    (.PA, .DE, .AS, .MI, .MC, .LS), USD sinon. Décision de Lucia du 24 novembre 2026."""
    return "EUR" if ticker.strip().upper().endswith(SUFFIXES_EUR) else "USD"


def devise_incertaine(ticker: str) -> bool:
    """Vrai quand devise_cotation rend USD par défaut pour un ticker qui n'est sans doute pas
    coté en dollars : indice hors États-Unis, paire de change ou paire crypto dont la devise de
    cotation n'est pas le dollar, autre suffixe de place."""
    t = ticker.strip().upper()
    if t.endswith(SUFFIXES_EUR):
        return False
    if t.startswith("^"):
        return t not in INDICES_USD
    if t.endswith("=X"):
        return not t[:-2].endswith("USD")
    if t.endswith("=F"):
        return False
    if "-" in t:
        cote = t.rsplit("-", 1)[1]
        return len(cote) >= 3 and cote != "USD"
    return "." in t
