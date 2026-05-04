"""
agents/fundamental_analyst/analyst.py — Sous-agent 2 : Fundamental Analyst
Produit une analyse fondamentale adaptée au type d'actif (crypto / action / indice).
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger import get_logger
from agents.analysts.fundamental_analyst.onchain import (
    TICKER_TO_COINGECKO, recuperer_donnees_coin, recuperer_dominance_btc,
    formater_grand_nombre, formater_pct, evaluer_crypto,
)
from agents.analysts.fundamental_analyst.macro import (
    recuperer_contexte_macro, position_52_semaines,
)

logger = get_logger(__name__)

ACTIONS_US     = {"AAPL", "TSLA", "NVDA", "MSFT", "AMZN"}
ETF_INDICES    = {"SPY", "QQQ", "VOO", "NQ=F", "GC=F"}


def detecter_type_actif(ticker: str) -> str:
    """Retourne 'crypto', 'action', 'etf_indice' selon le ticker."""
    if ticker in TICKER_TO_COINGECKO:
        return "crypto"
    if ticker in ACTIONS_US:
        return "action"
    if ticker in ETF_INDICES:
        return "etf_indice"
    return "inconnu"


def analyser_crypto(ticker: str) -> str:
    """Analyse fondamentale crypto via CoinGecko."""
    donnees  = recuperer_donnees_coin(ticker)
    if not donnees:
        return f"❌ Données CoinGecko indisponibles pour {ticker}"

    dominance = recuperer_dominance_btc()
    evaluation, impact, confiance = evaluer_crypto(donnees, dominance)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rapport = f"""
ANALYSE FONDAMENTALE — {ticker} — {now}
Type : Crypto ({donnees.get('nom')})
────────────────────────────────────────────────────────────
Données clés :
  - Rang market cap   : #{donnees.get('rang_market_cap', 'N/A')}
  - Market cap        : {formater_grand_nombre(donnees.get('market_cap'))}
  - Volume 24h        : {formater_grand_nombre(donnees.get('volume_24h'))}
  - Variation 24h     : {formater_pct(donnees.get('variation_24h'))}
  - Variation 7j      : {formater_pct(donnees.get('variation_7j'))}
  - Variation 30j     : {formater_pct(donnees.get('variation_30j'))}
  - ATH               : {formater_grand_nombre(donnees.get('ath'))}
  - Distance ATH      : {formater_pct(donnees.get('distance_ath_pct'))}
  - Dominance BTC     : {f'{dominance:.1f}%' if dominance else 'N/A'}
────────────────────────────────────────────────────────────
Évaluation       : {evaluation}
Impact attendu   : {impact}
Confiance        : {confiance}/10
"""
    return rapport.strip()


def _evaluer_action(pe, pct) -> tuple[str, str, int]:
    """Évaluation combinée P/E + position 52-sem."""
    if pe is not None and pe < 15 and pct is not None and pct < 30: return "Sous-évalué", "Positif", 7
    if pe is not None and pe > 35 and pct is not None and pct > 80: return "Sur-évalué", "Négatif", 6
    if pct is not None and pct >= 85: return "Sur-évalué (court terme)", "Négatif", 5
    if pct is not None and pct <= 15: return "Sous-évalué (court terme)", "Positif", 5
    return "Juste valeur", "Neutre", 4


def analyser_action(ticker: str) -> str:
    """Analyse fondamentale action via Alpha Vantage (OVERVIEW + EARNINGS) + position 52-sem."""
    from agents.analysts.fundamental_analyst.alphavantage import recuperer_overview, recuperer_dernier_earning
    ov = recuperer_overview(ticker)
    pos = position_52_semaines(ticker)
    if not ov and not pos:
        return f"❌ Données indisponibles pour {ticker}"
    earn = recuperer_dernier_earning(ticker) if ov else {}

    pe = ov.get("pe_ratio") if ov else None
    pct = pos["position_pct"] if pos else None
    evaluation, impact, confiance = _evaluer_action(pe, pct)
    f = lambda v: f"{v}" if v is not None else "N/A"
    mcap = ov.get("market_cap") if ov else None
    div  = ov.get("dividende") if ov else None
    surp = earn.get("surprise_pct") if earn else None

    earn_bloc = (f"  - Date              : {earn.get('date', 'N/A')}\n"
                 f"  - EPS estimé / réel : {f(earn.get('eps_estime'))} / {f(earn.get('eps_reporte'))}\n"
                 f"  - Surprise          : {f'{surp:+.1f}%' if surp is not None else 'N/A'}"
                 ) if earn else "  - Earnings indisponibles (rate-limit ou API indispo)"
    pos_bloc = (f"  - Range 52-sem      : {pos['low_52']:,.2f} → {pos['high_52']:,.2f}\n"
                f"  - Prix actuel       : {pos['prix']:,.2f} ({pct:.1f}% dans range)"
                ) if pos else "  - Données prix indisponibles"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""
ANALYSE FONDAMENTALE — {ticker} ({ov.get('nom') if ov else ticker}) — {now}
Type : Action US | Secteur : {ov.get('secteur') if ov else 'N/A'}
────────────────────────────────────────────────────────────
Ratios fondamentaux (Alpha Vantage) :
  - P/E / EPS         : {f(pe)} / {f(ov.get('eps') if ov else None)}
  - Market cap / Beta : {f'${mcap/1e9:.1f}B' if mcap else 'N/A'} / {f(ov.get('beta') if ov else None)}
  - Dividende         : {f'{div*100:.2f}%' if div else 'N/A'}
Dernier earning :
{earn_bloc}
Position 52-sem :
{pos_bloc}
────────────────────────────────────────────────────────────
Évaluation       : {evaluation}
Impact attendu   : {impact}
Confiance        : {confiance}/10
""".strip()


def analyser_etf_indice(ticker: str) -> str:
    """Analyse d'un ETF ou indice via le contexte macro."""
    pos   = position_52_semaines(ticker)
    macro = recuperer_contexte_macro()
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not pos:
        pos_str = "Données prix indisponibles"
        pct     = None
    else:
        pct = pos["position_pct"]
        pos_str = f"{pos['prix']:,.2f} ({pct:.1f}% dans range 52-sem: [{pos['low_52']:,.2f} – {pos['high_52']:,.2f}])"

    # Évaluation combinée : position + courbe des taux
    courbe = macro.get("courbe_2_10")
    if pct is not None and pct >= 85 and courbe is not None and courbe < 0:
        evaluation = "Sur-évalué (contexte récession)"
        impact     = "Négatif"
        confiance  = 6
    elif pct is not None and pct <= 20:
        evaluation = "Sous-évalué"
        impact     = "Positif"
        confiance  = 6
    else:
        evaluation = "Juste valeur"
        impact     = "Neutre"
        confiance  = 5

    rapport = f"""
ANALYSE FONDAMENTALE — {ticker} — {now}
Type : ETF / Indice
────────────────────────────────────────────────────────────
Position       : {pos_str}
────────────────────────────────────────────────────────────
Contexte macro US :
  - Fed Funds Rate : {f"{macro['fed_funds_rate']:.2f}%" if macro.get('fed_funds_rate') is not None else 'N/A'}
  - US 10Y Yield   : {f"{macro['us_10y']:.2f}%" if macro.get('us_10y') is not None else 'N/A'}
  - US 2Y Yield    : {f"{macro['us_2y']:.2f}%" if macro.get('us_2y') is not None else 'N/A'}
  - Courbe 2-10    : {macro.get('interpretation', 'N/A')}
────────────────────────────────────────────────────────────
Évaluation       : {evaluation}
Impact attendu   : {impact}
Confiance        : {confiance}/10
"""
    return rapport.strip()


def analyser_actif(ticker: str) -> str:
    """Dispatcher : route vers la fonction d'analyse selon le type d'actif."""
    type_actif = detecter_type_actif(ticker)
    if type_actif == "crypto":
        return analyser_crypto(ticker)
    if type_actif == "action":
        return analyser_action(ticker)
    if type_actif == "etf_indice":
        return analyser_etf_indice(ticker)
    return f"❌ Type d'actif inconnu pour {ticker}"


if __name__ == "__main__":
    print("\nAlphaSignal — Fundamental Analyst — Test\n")
    print(analyser_actif("BTC-USD"))
    print("\n")
    print(analyser_actif("AAPL"))
    print("\n")
    print(analyser_actif("SPY"))
