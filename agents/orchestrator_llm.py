"""
agents/orchestrator_llm.py — Narratifs Gemini pour les rapports (v5.3.7).
Transforme les sections structurées en synthèse en prose, ajoutée AVANT
les blocs détaillés pour un coup d'œil rapide.
Fallback gracieux : "" → la section narrative est simplement omise.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.gemini import ask_gemini, gemini_disponible


SYSTEM_PROMPT_DAILY = """Tu rédiges le RÉSUMÉ EXÉCUTIF du rapport quotidien d'AlphaSignal,
en français. Le lecteur est un utilisateur intermédiaire de paper trading qui
ouvre son rapport le matin.

Tu produis 5 à 8 phrases qui expriment :
- Le ton de la journée (calme / mouvementée / décisive / brouillée)
- 1-2 décisions/actifs marquants (avec ticker, décision, raison courte)
- L'état du portefeuille en une phrase (positions, P&L latent, mode)
- Le climat de marché en une phrase (F&G, dominance, corrélations clés)
- 1 angle à surveiller pour les prochains jours

INTERDICTIONS :
- Ne JAMAIS donner un nouveau prix, target, ordre buy/sell. Tu résumes.
- Ne JAMAIS inventer un chiffre absent du contexte
- Pas de blabla. Style direct."""


SYSTEM_PROMPT_WEEKLY = """Tu rédiges le RÉSUMÉ EXÉCUTIF du rapport hebdomadaire d'AlphaSignal,
en français. Le lecteur prend du recul une fois par semaine.

Tu produis 6 à 10 phrases avec :
- Verdict global de la semaine (gagnante, perdante, mitigée — avec winrate + P&L)
- 1-2 leçons concrètes tirées des trades clôturés (succès et erreurs)
- État du portefeuille (capital, positions, mode)
- Comment l'intuition a performé si applicable
- 1 axe de progression pour la semaine suivante

INTERDICTIONS :
- Ne JAMAIS donner d'ordre d'achat/vente
- Ne JAMAIS inventer de chiffres
- Style direct, factuel."""


def narratif_quotidien(decisions: list[dict], sentiment_global: dict,
                       etat: dict, monitor_resume: dict | None = None) -> str:
    """Résumé exécutif du rapport quotidien."""
    if not gemini_disponible():
        return ""

    buys  = [d for d in decisions if d["decision"]["decision"] == "BUY"]
    sells = [d for d in decisions if d["decision"]["decision"] == "SELL"]
    no_trades = [d for d in decisions if d["decision"]["decision"] == "NO_TRADE"]
    holds = [d for d in decisions if d["decision"]["decision"] == "HOLD"]

    def _resume(d):
        x = d["decision"]
        return (f"  {d['ticker']:10s} {x['decision']:8s} "
                f"score {x.get('score_composite', 0):+.2f} "
                f"conf {x.get('confidence', 0)}/10 — "
                f"{(x.get('reasoning') or '')[:150]}")

    parts = [
        f"== STATS DÉCISIONS ==",
        f"Total : {len(decisions)} | BUY : {len(buys)} | SELL : {len(sells)} | "
        f"NO_TRADE : {len(no_trades)} | HOLD : {len(holds)}",
        ""
    ]
    if buys or sells:
        parts.append("== BUY / SELL ==")
        for d in (buys + sells)[:6]:
            parts.append(_resume(d))
        parts.append("")
    if no_trades[:3]:
        parts.append("== NO_TRADE (override) ==")
        for d in no_trades[:3]:
            parts.append(_resume(d))
        parts.append("")

    parts.append("== PORTEFEUILLE ==")
    parts.append(
        f"Capital {etat.get('capital_total', 0):.0f}€ | "
        f"Investi {etat.get('invested', 0):.0f}€ | "
        f"Positions {etat.get('open_positions_count', 0)}/{etat.get('max_positions', 20)} | "
        f"P&L latent {etat.get('unrealized_pnl', 0):+.2f}€ | "
        f"Mode {'défensif' if etat.get('mode_defensif') else 'normal'}"
    )
    if monitor_resume:
        parts.append(f"Monitor : {monitor_resume.get('fermees', 0)} position(s) "
                     f"fermée(s) sur SL/TP aujourd'hui")
    parts.append("")

    parts.append("== MARCHÉ ==")
    parts.append(
        f"F&G {sentiment_global.get('fg_valeur', 'N/A')} "
        f"({sentiment_global.get('fg_label', '?')}) | "
        f"Dominance BTC {sentiment_global.get('dominance', 0):.1f}% | "
        f"Corr BTC/SPY {sentiment_global.get('corr_btc_spy', 0):+.2f}"
    )
    parts.append("")
    parts.append("Ton résumé exécutif (5-8 phrases) :")

    return ask_gemini("\n".join(parts), system=SYSTEM_PROMPT_DAILY,
                      temperature=0.5, max_output_tokens=700)


def narratif_hebdo(cette_sem: list[dict], etat: dict, intuition: dict) -> str:
    """Résumé exécutif du rapport hebdomadaire."""
    if not gemini_disponible():
        return ""
    nb = len(cette_sem)
    wins = sum(1 for p in cette_sem if (p.get("pnl_euros") or 0) > 0)
    pnl_total = sum((p.get("pnl_euros") or 0) for p in cette_sem)

    top = sorted(cette_sem, key=lambda p: (p.get("pnl_euros") or 0), reverse=True)
    parts = [
        f"== SEMAINE ==",
        f"Trades clôturés : {nb} ({wins} wins, {nb - wins} pertes)",
        f"Winrate : {(wins / nb * 100) if nb else 0:.1f}%  |  P&L semaine : {pnl_total:+.2f}€",
        ""
    ]
    if top:
        parts.append("== TOP 3 GAGNANTS ==")
        for p in top[:3]:
            parts.append(f"  {p.get('ticker', '?')} : {p.get('pnl_euros', 0):+.2f}€ "
                         f"({p.get('reason', '')[:80]})")
        parts.append("")
        if len(top) > 3:
            parts.append("== 3 PIRES ==")
            for p in top[-3:]:
                parts.append(f"  {p.get('ticker', '?')} : {p.get('pnl_euros', 0):+.2f}€ "
                             f"({p.get('reason', '')[:80]})")
            parts.append("")
    parts.append("== PORTEFEUILLE ==")
    parts.append(
        f"Capital {etat.get('capital_total', 0):.0f}€ | "
        f"Total value {etat.get('total_value', 0):.0f}€ | "
        f"Latent {etat.get('unrealized_pnl', 0):+.2f}€ | "
        f"Positions {etat.get('open_positions_count', 0)}/{etat.get('max_positions', 20)}"
    )
    parts.append("")
    parts.append("== INTUITION ==")
    wr = intuition.get("winrate_pct")
    parts.append(
        f"{intuition.get('total', 0)} décisions intuitives | "
        f"winrate {wr if wr is not None else 'N/A'}% | "
        f"en attente {intuition.get('en_attente', 0)}"
    )
    parts.append("")
    parts.append("Ton résumé exécutif (6-10 phrases) :")

    return ask_gemini("\n".join(parts), system=SYSTEM_PROMPT_WEEKLY,
                      temperature=0.5, max_output_tokens=900)
