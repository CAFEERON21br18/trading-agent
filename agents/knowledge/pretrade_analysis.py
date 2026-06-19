"""
agents/knowledge/pretrade_analysis.py — Analyse pré-trade approfondie v5.0
Produit l'analyse en 8 sections décrite dans le prompt v5.

Mode complet : appelé par cycle quotidien / stratégique / décisions importantes.
Mode condensé : appelé par cycle tactique (couches 1, 7, 8 seulement).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from agents.knowledge.chart_reading import analyser_graphique
from agents.knowledge.knowledge_base import concepts_pour_decision

logger = get_logger(__name__)


def analyse_pretrade(ticker: str, analyses: dict, decision: dict,
                     mode: str = "complet") -> dict:
    """
    Génère l'analyse pré-trade en 8 sections.
    Args:
        ticker : ticker analysé
        analyses : dict produit par asset_analyzer (technique/fond/sent/risque/memory/context)
        decision : dict produit par decision_engine
        mode : "complet" (8 sections) ou "condense" (1, 7, 8)
    """
    if mode == "condense":
        return _analyse_condensee(ticker, analyses, decision)

    chart = analyser_graphique(ticker, "1d")
    technique   = analyses.get("technique", {})
    fondamental = analyses.get("fondamental", {})
    sentiment   = analyses.get("sentiment", {})
    risque      = analyses.get("risque", {})
    memory      = analyses.get("memory", {})
    context     = analyses.get("context", {})

    # 1. Lecture graphique (multi-timeframe via chart_reading)
    section1 = {
        "tendance":   chart.get("structure", {}).get("tendance", "?"),
        "phase":      chart.get("structure", {}).get("phase", "?"),
        "weekly":     chart.get("mtf", {}).get("weekly", "?"),
        "niveaux":    chart.get("niveaux", {}),
        "patterns":   chart.get("patterns", {}).get("patterns", []),
        "divergence": chart.get("patterns", {}).get("divergence"),
        "confluence_score": chart.get("score_confluence", 0),
        "elements_alignes": chart.get("elements_confluence", []),
    }

    # 2. Fondamentaux
    section2 = {
        "evaluation":  fondamental.get("evaluation", "N/A"),
        "direction":   fondamental.get("direction", "NEUTRE"),
        "confiance":   fondamental.get("confiance", 0),
    }

    # 3. Catalyseurs (V1 : on n'a pas encore les earnings/guidance — placeholder)
    section3 = {
        "prochains_catalyseurs": "Earnings/guidance non implémentés (V2 Alpha Vantage)",
    }

    # 4. Contexte média/spéculatif
    section4 = {
        "sentiment_news": sentiment.get("narratif", "?"),
        "confiance":      sentiment.get("confiance", 0),
    }

    # 5. Macro
    section5 = {
        "fg_valeur":     context.get("fg_valeur"),
        "fg_label":      context.get("fg_label"),
        "dominance_btc": context.get("dominance"),
        "geopolitique":  context.get("categories", {}),
    }

    # 6. Psychologie
    fg = context.get("fg_valeur")
    if fg is not None and fg < 20:
        signal_contrarian = "Extreme Fear → potentiel d'accumulation"
    elif fg is not None and fg > 80:
        signal_contrarian = "Extreme Greed → prudence"
    else:
        signal_contrarian = "Pas de signal contrarian extrême"
    section6 = {"signal_contrarian": signal_contrarian}

    # 7. Gestion du risque
    risque_sig = risque.get("signal") if risque else None
    section7 = {
        "entree":     risque_sig.get("prix_entree") if risque_sig else None,
        "stop_loss":  risque_sig.get("stop_loss") if risque_sig else None,
        "target_1":   risque_sig.get("target_1") if risque_sig else None,
        "rr_1":       risque_sig.get("rr_1") if risque_sig else None,
        "taille":     risque_sig.get("taille_unites") if risque_sig else None,
        "risque_eur": risque_sig.get("montant_risque_reel") if risque_sig else None,
    }

    # 8. Synthèse & conviction
    perf = memory.get("perf") if memory else None
    lecons = memory.get("lecons", []) if memory else []
    principes = concepts_pour_decision(decision.get("decision", "HOLD"),
                                       decision.get("score_composite", 0),
                                       decision.get("confidence", 0))
    section8 = {
        "thèse":               decision.get("reasoning", ""),
        "conviction":          decision.get("confidence", 0),
        "decision":            decision.get("decision", "HOLD"),
        "style":               decision.get("style", "normal"),
        "memoire_winrate":     perf.get("winrate_pct") if perf else None,
        "memoire_trades":      perf.get("trades") if perf else None,
        "lecons_applicables":  len(lecons),
        "principes_appliques": principes,
    }

    return {
        "ticker":   ticker,
        "mode":     "complet",
        "1_lecture_graphique":   section1,
        "2_fondamentaux":        section2,
        "3_catalyseurs":         section3,
        "4_contexte_media":      section4,
        "5_macro_intermarches":  section5,
        "6_psychologie":         section6,
        "7_gestion_risque":      section7,
        "8_synthese_conviction": section8,
    }


def _analyse_condensee(ticker: str, analyses: dict, decision: dict) -> dict:
    """Version condensée pour cycles rapides : sections 1, 7, 8 uniquement."""
    technique = analyses.get("technique", {})
    risque    = analyses.get("risque", {})
    risque_sig = risque.get("signal") if risque else None

    return {
        "ticker": ticker,
        "mode":   "condense",
        "1_lecture_rapide": {
            "direction": technique.get("direction"),
            "confiance": technique.get("confiance"),
            "tendance":  technique.get("tendance"),
        },
        "7_gestion_risque": {
            "entree":    risque_sig.get("prix_entree") if risque_sig else None,
            "stop_loss": risque_sig.get("stop_loss") if risque_sig else None,
            "rr_1":      risque_sig.get("rr_1") if risque_sig else None,
        } if risque_sig else None,
        "8_synthese": {
            "decision":   decision.get("decision"),
            "conviction": decision.get("confidence"),
            "thèse":      decision.get("reasoning", "")[:200],
            "style":      decision.get("style", "normal"),
        },
    }


def formater_markdown(analyse: dict) -> str:
    """Format markdown pour rapport email / dashboard."""
    if "erreur" in analyse:
        return f"❌ {analyse['erreur']}"

    if analyse.get("mode") == "condense":
        s8 = analyse["8_synthese"]
        return (f"### {analyse['ticker']} — {s8['decision']} ({s8['conviction']}/10) "
                f"[{s8['style']}]\n{s8['thèse']}")

    lignes = [f"### Analyse pré-trade — {analyse['ticker']}"]
    s1 = analyse["1_lecture_graphique"]
    lignes.append(f"**1. Graphique** : {s1['tendance']} | {s1['phase']} | weekly: {s1['weekly']}")
    lignes.append(f"   Confluence : {s1['confluence_score']}/10 ({len(s1['elements_alignes'])} éléments)")
    if s1['patterns']:
        lignes.append(f"   Patterns : {', '.join(s1['patterns'])}")
    s2 = analyse["2_fondamentaux"]
    lignes.append(f"**2. Fondamentaux** : {s2['evaluation']} (conf {s2['confiance']}/10)")
    s4 = analyse["4_contexte_media"]
    lignes.append(f"**4. News** : {s4['sentiment_news']}")
    s5 = analyse["5_macro_intermarches"]
    lignes.append(f"**5. Macro** : F&G {s5['fg_valeur']} ({s5['fg_label']})")
    s6 = analyse["6_psychologie"]
    lignes.append(f"**6. Psycho** : {s6['signal_contrarian']}")
    s7 = analyse["7_gestion_risque"]
    if s7.get("entree"):
        lignes.append(f"**7. Risque** : entrée {s7['entree']:.2f} | SL {s7['stop_loss']:.2f} | TP1 {s7['target_1']:.2f} | R:R {s7['rr_1']:.1f}")
    s8 = analyse["8_synthese_conviction"]
    lignes.append(f"**8. Décision** : **{s8['decision']}** ({s8['conviction']}/10) [{s8['style']}]")
    lignes.append(f"   Thèse : {s8['thèse']}")
    if s8['memoire_winrate'] is not None:
        lignes.append(f"   Mémoire : winrate {s8['memoire_winrate']:.0f}% sur {s8['memoire_trades']} trades")
    return "\n".join(lignes)
