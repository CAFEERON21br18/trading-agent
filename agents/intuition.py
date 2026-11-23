"""
agents/intuition.py — Système d'intuition de l'agent
L'agent consulte sa mémoire (winrate historique, patterns, contexte géopolitique)
et peut s'écarter des indicateurs s'il a un "pressentiment" justifié.

L'intuition se construit sur 3 piliers :
1. MÉMOIRE : winrate par actif (memory_reader.consulter_memoire)
2. EXPÉRIENCE : patterns récurrents (market_patterns.md)
3. CONTEXTE : géopolitique (geopolitics.resume_contexte_geopolitique)
"""

import sys
import os
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.memoire_modeles import preparer as preparer_depuis_modele
from agents.memory_reader import consulter_memoire

logger = get_logger(__name__)

INTUITION_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "memory", "intuition_log.md",
)

# Seuils d'intuition
WINRATE_FORT_BUY     = 70.0  # ≥ 70% sur ce ticker → boost confiance
WINRATE_FAIBLE_AVOID = 35.0  # < 35% → pénalité
TRADES_MIN_SIGNIFICATIF = 3  # nb min trades pour considérer le winrate fiable


def consulter_intuition(ticker: str, analyses: dict, decision_preliminaire: str) -> dict:
    """
    Consulte la mémoire et le contexte pour ajuster la décision.

    Args:
        ticker : ex 'BTC-USD'
        analyses : dict produit par asset_analyzer
        decision_preliminaire : décision brute du Decision Engine (BUY/SELL/HOLD/NO_TRADE)

    Retourne :
        {
          "ajustement":       int (-2 à +2) : jamais ajouté au score composite ; il donne le
                              pressentiment et, à ±2, l'override ci-dessous ; écrit au journal,
          "pressentiment":    "haussier" | "baissier" | "neutre",
          "raisons":          list[str] (pourquoi l'agent a un pressentiment),
          "override_decision": str | None (si l'intuition force une décision),
          "boost_confiance":   int (-1 à +1, ajouté à la confiance finale),
        }
    """
    perf  = analyses.get("memory", {}).get("perf")
    raisons = []
    ajustement = 0
    boost_conf = 0
    override = None

    # ── 1. Winrate historique sur cet actif ──────────────────────────────────
    if perf and perf["trades"] >= TRADES_MIN_SIGNIFICATIF:
        wr = perf["winrate_pct"]
        if wr >= WINRATE_FORT_BUY:
            ajustement += 1
            boost_conf += 1
            raisons.append(f"Winrate excellent sur {ticker} : {wr:.0f}% ({perf['trades']} trades)")
        elif wr < WINRATE_FAIBLE_AVOID:
            ajustement -= 2
            boost_conf -= 1
            raisons.append(f"Winrate médiocre sur {ticker} : {wr:.0f}% — prudence")

    # ── 2. Patterns connus (memory) ─────────────────────────────────────────
    patterns = analyses.get("memory", {}).get("patterns", [])
    if patterns:
        raisons.append(f"{len(patterns)} pattern(s) connu(s) trouvé(s) en mémoire")
        ajustement += 1  # bonus modeste — un pattern documenté est un signal

    # ── 3. Leçons applicables ────────────────────────────────────────────────
    lecons = analyses.get("memory", {}).get("lecons", [])
    if lecons:
        raisons.append(f"{len(lecons)} leçon(s) historique(s) sur cet actif")

    # ── 4. Détermination du pressentiment ────────────────────────────────────
    if ajustement >= 2:
        pressentiment = "haussier"
    elif ajustement <= -2:
        pressentiment = "baissier"
    else:
        pressentiment = "neutre"

    # ── 5. Override possible ─────────────────────────────────────────────────
    # Si décision préliminaire HOLD/NO_TRADE mais intuition très forte → override BUY
    if decision_preliminaire in ("HOLD", "NO_TRADE") and ajustement >= 2:
        override = "BUY"
        raisons.append("Override intuitif : signaux modérés mais mémoire forte")
    # Si décision BUY/SELL mais intuition contraire forte → override NO_TRADE
    elif decision_preliminaire in ("BUY", "SELL") and ajustement <= -2:
        override = "NO_TRADE"
        raisons.append("Override intuitif : prudence due à mauvais historique")

    return {
        "ajustement":       ajustement,
        "pressentiment":    pressentiment,
        "raisons":          raisons,
        "override_decision": override,
        "boost_confiance":   boost_conf,
    }


def enregistrer_decision_intuitive(ticker: str, decision: dict, intuition: dict, position: dict | None = None) -> None:
    """
    Ajoute une entrée à intuition_log.md quand l'agent s'écarte des indicateurs.
    """
    if not (intuition.get("override_decision") or intuition["ajustement"] != 0):
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    score = decision.get("score_composite", 0)

    entree = (f"\n### {now} — {ticker} — {decision['decision']} (intuition)\n"
              f"- **Score indicateurs** : {score:+.2f} | Confiance ajustée : {decision['confidence']}/10\n"
              f"- **Pressentiment** : {intuition['pressentiment']} (ajustement {intuition['ajustement']:+d})\n"
              f"- **Raisons intuitives** :\n"
              + "\n".join(f"  - {r}" for r in intuition["raisons"]) + "\n")

    if intuition.get("override_decision"):
        entree += f"- **Override** : décision modifiée vers {intuition['override_decision']}\n"

    if position:
        entree += (f"- **Position** : {position.get('taille', '?')}u "
                   f"@ {position.get('prix', '?')} | SL {position.get('sl', '?')} "
                   f"| TP {position.get('tp', '?')}\n")

    entree += "- **Résultat** : ⏳ à remplir après clôture\n"

    try:
        preparer_depuis_modele(INTUITION_LOG)  # fichier hors git absent : créé depuis le modèle
        with open(INTUITION_LOG, "a", encoding="utf-8") as f:
            f.write(entree)
        logger.info(f"Décision intuitive enregistrée pour {ticker}")
    except Exception as e:
        logger.error(f"Écriture intuition_log échouée : {e}")


def journaliser_intuition(ticker: str, resultat: dict, intuition: dict, origine: str = "cycle") -> None:
    """Étape 4 du Decision Engine, journal SEULEMENT : quand l'intuition modifie (override) ou
    ajuste la décision d'un cycle, une entrée dans intuition_log.md (miroir : vault, 30-Intuitions).
    Rien n'est rendu ni modifié ; toute erreur est journalisée et n'interrompt jamais le moteur.
    Hors cycles, rien : le chat n'écrit pas (E2) et les actifs du conseiller sont ceux du portefeuille
    réel (intuition_log.md est suivi par git). Une entrée par actif, jour (UTC) et décision : le
    tactical repasse toutes les 15 minutes."""
    try:
        if origine != "cycle" or not (intuition.get("override_decision") or intuition.get("ajustement")):
            return
        jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        deja = re.compile(rf"^### {jour} \d\d:\d\d UTC — {re.escape(ticker)} — "
                          rf"{re.escape(str(resultat.get('decision')))} \(intuition\)", re.M)
        if os.path.exists(INTUITION_LOG):
            with open(INTUITION_LOG, encoding="utf-8") as f:
                if deja.search(f.read()):
                    return
        enregistrer_decision_intuitive(ticker, resultat, intuition)
    except Exception as e:
        logger.warning(f"Journal d'intuition {ticker} non écrit (le moteur continue) : {e}")
