"""
agents/orchestrator.py — Orchestrateur principal d'AlphaSignal
Coordonne les 6 sous-agents, génère le rapport quotidien, envoie les alertes.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.logger     import get_logger
from utils.helpers    import charger_watchlist, tous_les_tickers, sauvegarder_rapport
from agents.analysts.sentiment_analyst.analyst    import recuperer_fear_greed_crypto, calculer_correlation
from agents.analysts.fundamental_analyst.onchain  import recuperer_dominance_btc
from agents.asset_analyzer               import analyser_actif_complet
from agents.decision_engine              import decider
from agents.decision_formatter           import formater_decision
from agents.paper_trader.cycle           import (
    initialiser as init_paper, executer_ouvertures, enregistrer_snapshot_quotidien,
    formater_section_portefeuille,
)
from agents.paper_trader.monitor         import monitorer_positions
from agents.paper_trader.portfolio       import etat_portefeuille
from agents.trade_journalist.journalist  import enregistrer_signal
from agents.trade_journalist.performance_tracker import (
    mettre_a_jour_performance_md, verifier_alerte_degradation,
)
from alerts.alert_manager                import (
    envoyer_rapport_quotidien, envoyer_alerte_signal_fort,
    envoyer_alerte_extreme_fear_greed, envoyer_alerte_degradation,
)

logger = get_logger(__name__)


def _signal_depuis_analyses(ticker: str, analyses: dict) -> dict:
    """Adapte le résultat d'analyser_actif_complet au format 'signal' attendu par le tableau."""
    t = analyses["technique"]
    return {
        "ticker":    ticker,
        "signal":    t["direction"],
        "confiance": t["confiance"],
        "prix":      t["prix"],
        "tendance":  t.get("tendance", "Neutre"),
        "motifs":    t.get("motifs", []),
    }


def generer_resume_30s(decisions: list[dict], sentiment_global: dict) -> str:
    """Résumé '30 secondes' en tête du rapport — basé sur les décisions du Decision Engine."""
    nb_buy  = sum(1 for d in decisions if d["decision"]["decision"] == "BUY")
    nb_sell = sum(1 for d in decisions if d["decision"]["decision"] == "SELL")
    nb_hold = sum(1 for d in decisions if d["decision"]["decision"] == "HOLD")
    nb_no   = sum(1 for d in decisions if d["decision"]["decision"] == "NO_TRADE")

    fg_val   = sentiment_global.get("fg_valeur")
    fg_label = sentiment_global.get("fg_label", "")

    actifs = [d for d in decisions if d["decision"]["decision"] in ("BUY", "SELL")]
    lignes = [
        f"- **Décisions** : {nb_buy} BUY, {nb_sell} SELL, {nb_hold} HOLD, {nb_no} NO_TRADE",
        f"- **Fear & Greed** : {fg_val} ({fg_label})" if fg_val else "- **Fear & Greed** : N/A",
    ]
    if actifs:
        lignes.append("- **Décisions actives** :")
        for d in actifs:
            dec = d["decision"]
            lignes.append(f"  - {dec['ticker']} {dec['decision']} ({dec['confidence']}/10)")
    else:
        lignes.append("- **Aucune décision active aujourd'hui** (tout en HOLD ou NO_TRADE)")
    return "\n".join(lignes)


def generer_tableau_watchlist(decisions: list[dict]) -> str:
    """Tableau récapitulatif : technique + décision finale par actif."""
    lignes = ["| Actif | Tech (signal/conf) | Score | Décision finale | Conf. |",
              "|-------|--------------------|-------|-----------------|-------|"]
    for d in decisions:
        t = d["analyses"]["technique"]
        dec = d["decision"]
        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "NO_TRADE": "⚪"}.get(dec["decision"], "")
        lignes.append(
            f"| {dec['ticker']} | {t['direction']} {t['confiance']}/10 | "
            f"{dec['score_composite']:+.2f} | {emoji} {dec['decision']} | {dec['confidence']}/10 |"
        )
    return "\n".join(lignes)


def generer_rapport_quotidien() -> tuple[str, list[dict], list[dict]]:
    """
    Routine complète : monitor → analyses → decisions → cycle paper → snapshot → rapport.
    Retourne (rapport_md, decisions_actives, all_decisions).
    """
    logger.info("Génération du rapport quotidien (Decision Engine + Paper Trading)...")
    now      = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    # ── 0. Init paper DB + monitor des positions existantes (fermeture SL/TP) ──
    init_paper()
    monitor_resume = monitorer_positions()

    # ── 1. Sentiment global ──────────────────────────────────────────────────
    fg = recuperer_fear_greed_crypto()
    sentiment_global = {
        "fg_valeur":    fg.get("valeur"),
        "fg_label":     fg.get("label"),
        "dominance":    recuperer_dominance_btc(),
        "corr_btc_spy": calculer_correlation("BTC-USD", "SPY"),
    }

    # ── 2. Decision Engine sur toute la watchlist ────────────────────────────
    watchlist = charger_watchlist()
    tickers   = tous_les_tickers(watchlist)
    decisions = []
    for ticker in tickers:
        try:
            analyses = analyser_actif_complet(ticker, sentiment_global)
            decision = decider(ticker, analyses)
            decisions.append({"ticker": ticker, "decision": decision, "analyses": analyses})
        except Exception as e:
            logger.error(f"Decision Engine {ticker} échoué : {e}")

    actifs_buy_sell = [d for d in decisions if d["decision"]["decision"] in ("BUY", "SELL")]

    # ── 3. Cycle paper : ouvrir les nouvelles positions ──────────────────────
    cycle_resume = executer_ouvertures(decisions)

    # ── 4. Snapshot quotidien du portefeuille ────────────────────────────────
    enregistrer_snapshot_quotidien()
    etat = etat_portefeuille()

    # ── 5. Construction du rapport ───────────────────────────────────────────
    section_paper = formater_section_portefeuille(etat, monitor_resume, cycle_resume)
    section_decisions = "\n\n---\n\n".join(
        formater_decision(d["decision"], d["analyses"]) for d in decisions
    )
    rapport = f"""# AlphaSignal — Rapport Quotidien — {date_str}

Généré le : {now.strftime("%Y-%m-%d %H:%M UTC")}
Capital total : {config.CAPITAL:.0f}€ | Investissable : {config.CAPITAL_INVESTISSABLE:.0f}€ \
({config.MAX_CAPITAL_INVESTI_PCT:.0f}%) | Risque/trade : {config.RISK_PER_TRADE_PCT:.1f}%

## ⚡ État du marché en 30 secondes

{generer_resume_30s(decisions, sentiment_global)}

## 📊 Watchlist — Vue d'ensemble (Decision Engine)

{generer_tableau_watchlist(decisions)}

{section_paper}

## 🌐 Sentiment & Contexte

- **Fear & Greed Crypto** : {sentiment_global['fg_valeur']} ({sentiment_global['fg_label']})
- **Dominance BTC** : {f"{sentiment_global['dominance']:.1f}%" if sentiment_global['dominance'] else 'N/A'}
- **Corrélation BTC/SPY (60j)** : {f"{sentiment_global['corr_btc_spy']:+.2f}" if sentiment_global['corr_btc_spy'] is not None else 'N/A'}

## 🧠 Décisions par actif

{section_decisions}

## ⚠️ Disclaimer

Les analyses fournies sont à titre informatif uniquement. Toutes les décisions de trading
sont en mode **paper trading** (simulé) — aucun ordre réel n'est exécuté sur Revolut.
"""
    sauvegarder_rapport(rapport, dossier="daily")
    return rapport, actifs_buy_sell, decisions


def lancer_routine_quotidienne(envoyer_emails: bool = True) -> dict:
    """
    Routine quotidienne complète : analyses + rapport + alertes + mémoire.
    Retourne un résumé des actions effectuées.
    """
    resume = {
        "signaux_detectes":      0,
        "signaux_forts":         0,
        "rapport_envoye":        False,
        "alertes_envoyees":      0,
        "alerte_degradation":    False,
    }

    # ── Vérification capital ─────────────────────────────────────────────────
    if config.CAPITAL <= config.CAPITAL_STOP_THRESHOLD:
        logger.warning("Capital sous le seuil d'arrêt — routine suspendue")
        return resume

    # ── Génération rapport (monitor + Decision Engine + cycle paper) ────────
    rapport_md, decisions_actives, _ = generer_rapport_quotidien()
    resume["signaux_forts"] = len(decisions_actives)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Enregistrement des décisions BUY/SELL dans le journal ──────────────
    for d in decisions_actives:
        dec = d["decision"]
        risk = d["analyses"]["risque"]
        if not (risk.get("valide") and risk.get("signal")):
            continue
        direction = "LONG" if dec["decision"] == "BUY" else "SHORT"
        sig = risk["signal"]
        enregistrer_signal(
            ticker=dec["ticker"], direction=direction,
            confiance=dec["confidence"],
            prix_signal=d["analyses"]["technique"]["prix"],
            stop_loss=sig["stop_loss"],
            target_1=sig["target_1"], target_2=sig["target_2"],
            timeframe="1d",
            source_agents="Decision Engine",
            raison=dec["reasoning"],
        )

    # ── Envoi email rapport ──────────────────────────────────────────────────
    if envoyer_emails:
        if envoyer_rapport_quotidien(rapport_md, date_str):
            resume["rapport_envoye"] = True

        # Alertes immédiates — décisions BUY/SELL avec confiance ≥ seuil
        for d in decisions_actives:
            dec = d["decision"]
            if dec["confidence"] < config.ALERT_CONFIDENCE_THRESHOLD:
                continue
            direction = "LONG" if dec["decision"] == "BUY" else "SHORT"
            prix = d["analyses"]["technique"]["prix"]
            details = (f"Score composite : {dec['score_composite']:+.2f}\n"
                       f"Raisonnement : {dec['reasoning']}\n"
                       f"Convergences : {len(dec['convergences'])} | "
                       f"Contradictions : {len(dec['contradictions'])}")
            if envoyer_alerte_signal_fort(dec["ticker"], direction, dec["confidence"], prix, details):
                resume["alertes_envoyees"] += 1

        # Alerte F&G extrême
        fg = recuperer_fear_greed_crypto()
        if fg.get("valeur") is not None:
            if envoyer_alerte_extreme_fear_greed(fg["valeur"], fg["label"]):
                resume["alertes_envoyees"] += 1

    # ── Mise à jour performance et mémoire ──────────────────────────────────
    mettre_a_jour_performance_md()

    # ── Alerte dégradation ───────────────────────────────────────────────────
    alerte, msg = verifier_alerte_degradation()
    if alerte and envoyer_emails:
        envoyer_alerte_degradation(msg)
        resume["alerte_degradation"] = True

    logger.info(f"Routine quotidienne terminée : {resume}")
    return resume
