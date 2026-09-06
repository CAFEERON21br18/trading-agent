"""
agents/technical_skills/backtester_pro.py — Skill 9 : backtester renforcé.

Renforce agents/backtester existant avec :
- Split in-sample / out-of-sample (détecter l'overfitting)
- Filtre qualité (Sharpe > 0.5 ET profit_factor > 1.3)
- Comparaison vs buy & hold

Python pur (pandas). Réutilise agents/backtester/{engine, metrics}.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs
from agents.backtester.engine import (
    run_backtest, rendement_buy_and_hold,
    strategie_ema_20_50, strategie_ema_50_200, strategie_rsi_trend,
    strategie_bollinger_reversion, strategie_macd_adx,
)
from agents.backtester.metrics import calculer_metriques

logger = get_logger(__name__)

STRATEGIES = {
    "ema_20_50":          strategie_ema_20_50,
    "ema_50_200":         strategie_ema_50_200,
    "rsi_trend":          strategie_rsi_trend,
    "bollinger_revers":   strategie_bollinger_reversion,
    "macd_adx":           strategie_macd_adx,
}

# Seuils qualité (une strat "valide" les respecte sur out-of-sample)
SEUIL_SHARPE = 0.5
SEUIL_PROFIT_FACTOR = 1.3


def _split_in_out(df, ratio_in: float = 0.7):
    """Coupe l'historique en 70% in-sample / 30% out-of-sample."""
    n = len(df)
    cut = int(n * ratio_in)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def backtester_avec_validation(ticker: str, strategie_key: str,
                                timeframe: str = "1d",
                                lookback: int = 1000) -> dict:
    """Backtest complet avec split in-sample / out-of-sample.
    Retourne {ticker, strategie, in_sample, out_of_sample, buy_hold,
              overfitting, valide, verdict}."""
    if strategie_key not in STRATEGIES:
        return {"error": f"strategie inconnue : {strategie_key}",
                "dispo": list(STRATEGIES.keys())}

    df = charger_ohlcv(ticker, timeframe, limite=lookback)
    if df.empty or len(df) < 300:
        return {"error": f"< 300 bougies dispo pour {ticker}", "n": len(df)}

    # Indicateurs calculés sur l'historique complet avant split (comme
    # le backtester existant), puis dropna pour éviter les NaN de warmup.
    df = calculer_tous_indicateurs(df).dropna().copy()
    if len(df) < 200:
        return {"error": f"< 200 bougies après dropna pour {ticker}", "n": len(df)}

    in_df, out_df = _split_in_out(df, ratio_in=0.7)
    fn = STRATEGIES[strategie_key]

    # run_backtest retourne (trades, equity_curve) — pas un dict
    try:
        trades_in,  equity_in  = run_backtest(in_df,  fn)
        trades_out, equity_out = run_backtest(out_df, fn)
    except Exception as e:
        return {"error": f"backtest échoué : {e}"}

    m_in  = calculer_metriques(trades_in,  equity_in,  1000)
    m_out = calculer_metriques(trades_out, equity_out, 1000)
    bh_in  = rendement_buy_and_hold(in_df)
    bh_out = rendement_buy_and_hold(out_df)

    # Détection overfitting : Sharpe out < 50% Sharpe in
    sharpe_in  = m_in.get("sharpe_ratio", 0)
    sharpe_out = m_out.get("sharpe_ratio", 0)
    overfitting = (sharpe_in > 0 and sharpe_out < sharpe_in * 0.5)

    # Validation : la strat "survit" out-of-sample
    pf_out = m_out.get("profit_factor", 0)
    valide = (sharpe_out >= SEUIL_SHARPE and pf_out >= SEUIL_PROFIT_FACTOR)

    if valide and not overfitting:
        verdict = "VALIDE"
    elif overfitting:
        verdict = "OVERFITTING"
    elif not valide:
        verdict = "INSUFFISANTE"
    else:
        verdict = "DOUTEUX"

    return {
        "ticker":         ticker,
        "strategie":      strategie_key,
        "in_sample": {
            "nb_trades":    m_in.get("nb_trades", 0),
            "win_rate":     round(m_in.get("win_rate", 0), 1),
            "profit_factor": round(m_in.get("profit_factor", 0), 2),
            "sharpe":       round(sharpe_in, 2),
            "rendement_pct": round(m_in.get("rendement_total_pct", 0), 2),
            "max_dd_pct":   round(m_in.get("max_drawdown_pct", 0), 2),
        },
        "out_of_sample": {
            "nb_trades":    m_out.get("nb_trades", 0),
            "win_rate":     round(m_out.get("win_rate", 0), 1),
            "profit_factor": round(pf_out, 2),
            "sharpe":       round(sharpe_out, 2),
            "rendement_pct": round(m_out.get("rendement_total_pct", 0), 2),
            "max_dd_pct":   round(m_out.get("max_drawdown_pct", 0), 2),
        },
        "buy_hold": {
            "in_sample_pct":     round(bh_in, 2),
            "out_of_sample_pct": round(bh_out, 2),
        },
        "overfitting":  overfitting,
        "valide":       valide,
        "verdict":      verdict,
    }


def tester_toutes_strategies_avec_validation(ticker: str,
                                              timeframe: str = "1d") -> list[dict]:
    """Passe les 5 stratégies sur le ticker + validation in/out. Trié par Sharpe out."""
    results = []
    for key in STRATEGIES:
        r = backtester_avec_validation(ticker, key, timeframe)
        if "error" not in r:
            results.append(r)
    results.sort(key=lambda x: x["out_of_sample"]["sharpe"], reverse=True)
    return results
