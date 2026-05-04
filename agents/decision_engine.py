"""
agents/decision_engine.py — Moteur de décision unifié d'AlphaSignal
Reçoit les analyses des sous-agents, les croise, détecte convergences/contradictions,
vérifie les overrides et la mémoire, produit UNE décision argumentée.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Pondérations (somme = 100%) ──────────────────────────────────────────────
POIDS = {"technique": 0.35, "fondamental": 0.25, "sentiment": 0.20, "risque": 0.20}

# ── Seuils de décision (v4.1 — moins prudent pour favoriser l'apprentissage) ──
SEUIL_BUY              = 2.0   # BUY normal si score ≥ +2.0 (avant : +3.0)
SEUIL_SELL             = -2.0  # SELL normal si score ≤ -2.0 (avant : -3.0)
SEUIL_LEARNING         = 0.5   # BUY/SELL learning (micro-position) si |score| ≥ 0.5
SEUIL_CONTRADICTION    = 8     # contradiction majeure : confiance ≥ 8/10 (avant : 7)
WINRATE_PRUDENCE       = 35.0  # win rate sous lequel on exige confiance plus élevée
TAILLE_LEARNING_PCT    = 0.2   # micro-position = 20% du budget alloué
TAILLE_CONTRADICTION   = 0.5   # si contradiction → taille réduite à 50%


def _direction_a_signe(direction: str) -> int:
    """BULLISH/ACHAT → +1, BEARISH/VENTE → -1, NEUTRE/HOLD → 0."""
    d = (direction or "").upper()
    if d in ("BULLISH", "ACHAT", "BUY", "LONG", "POSITIF"):
        return 1
    if d in ("BEARISH", "VENTE", "SELL", "SHORT", "NÉGATIF", "NEGATIF"):
        return -1
    return 0


def _normaliser(analyses: dict) -> dict:
    """Pour chaque sous-agent : signe × confiance × poids = score."""
    scores = {}
    for nom, poids in POIDS.items():
        a = analyses.get(nom, {})
        signe     = _direction_a_signe(a.get("direction", "NEUTRE"))
        confiance = float(a.get("confiance", 0) or 0)
        scores[nom] = signe * confiance * poids
    return scores


def _convergences_contradictions(analyses: dict) -> tuple[list[str], list[str]]:
    """Identifie les paires d'agents qui convergent ou se contredisent."""
    convergences   = []
    contradictions = []
    noms = ["technique", "fondamental", "sentiment"]
    for i, n1 in enumerate(noms):
        for n2 in noms[i + 1:]:
            a1, a2 = analyses.get(n1, {}), analyses.get(n2, {})
            s1, s2 = _direction_a_signe(a1.get("direction")), _direction_a_signe(a2.get("direction"))
            c1, c2 = float(a1.get("confiance", 0) or 0), float(a2.get("confiance", 0) or 0)
            if s1 != 0 and s1 == s2 and c1 >= 5 and c2 >= 5:
                sens = "haussière" if s1 > 0 else "baissière"
                convergences.append(f"{n1.capitalize()} + {n2} convergent ({sens}, confiance {c1:.0f}/{c2:.0f})")
            elif s1 != 0 and s2 != 0 and s1 != s2 and c1 >= SEUIL_CONTRADICTION and c2 >= SEUIL_CONTRADICTION:
                contradictions.append(f"{n1.capitalize()} ({a1.get('direction')}) ⚠️ {n2} ({a2.get('direction')}) — confiance {c1:.0f}/{c2:.0f}")
    return convergences, contradictions


def _verifier_overrides(ticker: str, analyses: dict) -> list[str]:
    """Liste les facteurs qui BLOQUENT le trade (veto)."""
    overrides = []

    # Risk Manager veto
    risque = analyses.get("risque", {})
    if risque and not risque.get("valide", True):
        rejets = risque.get("rejets", [])
        overrides.append(f"Risk Manager rejette : {' | '.join(rejets)}")

    # Mauvais track record sur cet actif
    perf = analyses.get("memory", {}).get("perf")
    if perf and perf["trades"] >= 5 and perf["winrate_pct"] < WINRATE_PRUDENCE:
        overrides.append(
            f"Track record défavorable sur {ticker} : {perf['winrate_pct']:.0f}% "
            f"de winrate sur {perf['trades']} trades"
        )

    # Fear & Greed extrême combiné à un signal contraire (contrarian)
    ctx = analyses.get("context", {})
    fg = ctx.get("fg_valeur")
    tech_dir = _direction_a_signe(analyses.get("technique", {}).get("direction"))
    if fg is not None:
        if fg <= 20 and tech_dir < 0:
            overrides.append(f"Extreme Fear (F&G {fg}) contredit signal VENTE — possible bottom")
        elif fg >= 80 and tech_dir > 0:
            overrides.append(f"Extreme Greed (F&G {fg}) contredit signal ACHAT — possible top")

    return overrides


def _seuil_confiance_requis(analyses: dict) -> int:
    """Si winrate faible mais > 0 sur cet actif, exige confiance plus élevée."""
    perf = analyses.get("memory", {}).get("perf")
    if perf and perf["trades"] >= 3 and perf["winrate_pct"] < WINRATE_PRUDENCE:
        return 9
    return 7


def decider(ticker: str, analyses: dict) -> dict:
    """
    Entrée principale du Decision Engine — 5 étapes (v4) :
      1. Collecter & normaliser
      2. Corréler (convergences / contradictions)
      3. Vérifier les overrides
      4. Consulter l'intuition (mémoire + contexte)
      5. Décider et logger
    """
    scores      = _normaliser(analyses)
    score_total = round(sum(scores.values()), 2)
    convergences, contradictions = _convergences_contradictions(analyses)
    overrides   = _verifier_overrides(ticker, analyses)
    seuil_conf  = _seuil_confiance_requis(analyses)

    # Style de trading et facteur de taille (v4.1)
    style = "normal"
    taille_factor = 1.0

    # ── Décision préliminaire (v4.1 — contradictions ne bloquent plus) ───────
    if overrides:
        decision = "NO_TRADE"
        raison   = f"Override actif : {overrides[0]}"
    elif score_total >= SEUIL_BUY:
        decision = "BUY"
        raison   = f"Score composite +{score_total} ≥ {SEUIL_BUY}, signaux cohérents"
    elif score_total <= SEUIL_SELL:
        decision = "SELL"
        raison   = f"Score composite {score_total} ≤ {SEUIL_SELL}, signaux baissiers"
    elif score_total >= SEUIL_LEARNING:
        # Trade d'apprentissage — micro-position
        decision = "BUY"
        style    = "learning"
        taille_factor = TAILLE_LEARNING_PCT
        raison   = f"Score composite +{score_total} faible — trade d'apprentissage (micro-position)"
    elif score_total <= -SEUIL_LEARNING:
        decision = "SELL"
        style    = "learning"
        taille_factor = TAILLE_LEARNING_PCT
        raison   = f"Score composite {score_total} faible — trade d'apprentissage short (micro-position)"
    else:
        decision = "HOLD"
        raison   = f"Score composite {score_total} dans la zone neutre — pas d'avantage détecté"

    # Contradictions : ne bloquent plus, mais réduisent la taille
    if contradictions and decision in ("BUY", "SELL"):
        taille_factor *= TAILLE_CONTRADICTION
        raison += f" | ⚠️ Taille -{int((1 - TAILLE_CONTRADICTION) * 100)}% à cause d'une contradiction"

    # ── Étape 4 — Consulter l'intuition (peut override la décision) ──────────
    from agents.intuition import consulter_intuition
    intuition = consulter_intuition(ticker, analyses, decision)
    if intuition.get("override_decision"):
        ancienne = decision
        decision = intuition["override_decision"]
        if decision in ("BUY", "SELL") and ancienne in ("HOLD", "NO_TRADE"):
            style = "learning"  # override intuitif → micro-position pour prudence
            taille_factor = TAILLE_LEARNING_PCT
        raison = f"Intuition override ({ancienne} → {decision}) : {intuition['raisons'][0]}"

    # ── Confiance finale (avec boost intuition) ──────────────────────────────
    conf_max = max(float(analyses.get(k, {}).get("confiance", 0) or 0) for k in POIDS)
    conf_finale = min(10, conf_max + len(convergences) + intuition.get("boost_confiance", 0))
    if decision == "NO_TRADE":
        conf_finale = max(1, int(conf_max))

    return {
        "ticker":           ticker,
        "decision":         decision,
        "style":            style,           # "normal" | "learning"
        "taille_factor":    taille_factor,   # 1.0 (normal), 0.5 (contradiction), 0.2 (learning)
        "confidence":       int(conf_finale),
        "score_composite":  score_total,
        "scores_detail":    scores,
        "reasoning":        raison,
        "convergences":     convergences,
        "contradictions":   contradictions,
        "overrides":        overrides,
        "seuil_confiance_requis": seuil_conf,
        "intuition":        intuition,
    }
