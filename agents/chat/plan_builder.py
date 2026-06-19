"""
agents/chat/plan_builder.py — Création conversationnelle de plans (v5.1)
État machine simple : sessions stockées en mémoire process, identifiées par session_id.
Pas de LLM externe : poser les bonnes questions dans le bon ordre.
"""

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.real_portfolio_db import creer_plan, get_real_budget_summary

logger = get_logger(__name__)

# Sessions en mémoire : { session_id: {étape: "...", brouillon: {...}} }
SESSIONS: dict[str, dict] = {}

ETAPES = [
    "type",        # "Quel type de plan ?" (long_terme, court_terme, crypto, actions, cfd, custom)
    "nom",         # "Nom du plan ?"
    "budget",      # "Quel budget allouer ?"
    "objectif",    # "Quel rendement vise-tu ? (en %)"
    "horizon",     # "Sur quelle durée ?"
    "vision",      # "Philosophie / règles principales ?"
    "valider",     # Récap + confirmation
]


TYPES_VALIDES = {"long_terme", "court_terme", "actions", "crypto", "cfd", "custom"}


def _detecter_type(message: str) -> str | None:
    """Détecte le type de plan depuis un message libre."""
    m = message.lower()
    if "long" in m or "buy" in m or "hold" in m or "passif" in m: return "long_terme"
    if "court" in m or "swing" in m or "day" in m or "scalp" in m: return "court_terme"
    if "action" in m or "stock" in m or "equity" in m: return "actions"
    if "crypto" in m or "btc" in m or "eth" in m: return "crypto"
    if "cfd" in m or "levier" in m or "futures" in m: return "cfd"
    return None


def _detecter_nombre(message: str) -> float | None:
    """Extrait le 1er nombre du message (avec euro/pct/etc.)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", message.replace(" ", ""))
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _nouveau_brouillon(session_id: str) -> dict:
    s = {"etape": "type", "brouillon": {}}
    SESSIONS[session_id] = s
    return s


def _terminer(session_id: str, plan_id: int) -> dict:
    SESSIONS.pop(session_id, None)
    return {
        "etat":     "termine",
        "plan_id":  plan_id,
        "reponse":  f"✅ Plan créé (id #{plan_id}) ! Il apparaîtra dans la page 'Plans'.",
    }


def etape_creation_plan(session_id: str, message: str) -> dict:
    """
    État machine de création de plan.
    1er appel sans session → démarre la conversation.
    Appels suivants → progresse dans les étapes.
    """
    session = SESSIONS.get(session_id)

    # Démarrage
    if session is None or message.strip().lower() in ("nouveau", "start", "recommencer"):
        session = _nouveau_brouillon(session_id)
        budget = get_real_budget_summary()
        return {
            "etat":  "en_cours",
            "etape": "type",
            "reponse": (
                "Très bien, construisons un plan ensemble. Quel type de plan ?\n\n"
                "• `long_terme` (HODL, position trading)\n"
                "• `court_terme` (swing, day trading)\n"
                "• `actions` / `crypto` / `cfd`\n"
                "• `custom` (à toi de définir)\n\n"
                f"💰 Budget disponible : {budget.get('available', 0):.0f}€ "
                f"(sur capital total {budget.get('total_capital', 0):.0f}€)"
            ),
        }

    etape = session["etape"]
    brouillon = session["brouillon"]

    # Étape TYPE
    if etape == "type":
        t = _detecter_type(message) or message.strip().lower()
        if t not in TYPES_VALIDES:
            return {"etat": "en_cours", "etape": "type",
                    "reponse": "Type non reconnu. Réponds avec : long_terme, court_terme, actions, crypto, cfd, custom."}
        brouillon["plan_type"] = t
        session["etape"] = "nom"
        return {"etat": "en_cours", "etape": "nom",
                "reponse": f"OK, plan {t}. Quel nom veux-tu lui donner ? (ex: 'Crypto majeures 2026')"}

    # Étape NOM
    if etape == "nom":
        brouillon["name"] = message.strip()[:80]
        session["etape"] = "budget"
        return {"etat": "en_cours", "etape": "budget",
                "reponse": "Quel budget veux-tu allouer à ce plan (en €) ?"}

    # Étape BUDGET
    if etape == "budget":
        b = _detecter_nombre(message)
        if b is None or b <= 0:
            return {"etat": "en_cours", "etape": "budget",
                    "reponse": "Montant invalide. Indique un nombre en euros (ex: '300' ou '500€')."}
        brouillon["allocated_budget"] = b
        session["etape"] = "objectif"
        return {"etat": "en_cours", "etape": "objectif",
                "reponse": f"Budget alloué : {b:.0f}€. Quel rendement cible (en %) ? "
                           "(ex: '50' pour +50%, ou '100' pour doubler)"}

    # Étape OBJECTIF
    if etape == "objectif":
        r = _detecter_nombre(message)
        if r is None:
            return {"etat": "en_cours", "etape": "objectif",
                    "reponse": "Indique un % de rendement cible (ex: 30, 50, 100)."}
        brouillon["target_return_percent"] = r
        brouillon["target_amount"] = brouillon["allocated_budget"] * (1 + r / 100)
        session["etape"] = "horizon"
        return {"etat": "en_cours", "etape": "horizon",
                "reponse": f"Objectif : +{r:.0f}% → {brouillon['target_amount']:.0f}€. "
                           "Sur quelle durée ? (ex: '6 mois', '1 an', '2 ans')"}

    # Étape HORIZON
    if etape == "horizon":
        brouillon["time_horizon"] = message.strip()[:40]
        session["etape"] = "vision"
        return {"etat": "en_cours", "etape": "vision",
                "reponse": "Décris ta vision / philosophie de ce plan en quelques phrases. "
                           "(ex: 'majeures crypto + qq alts solides, DCA, éviter les meme coins')"}

    # Étape VISION
    if etape == "vision":
        brouillon["vision"] = message.strip()[:500]
        brouillon["risk_tolerance"] = "moyenne"  # par défaut
        # Taille max d'une position = 30% du budget (heuristique sensée)
        brouillon["max_position_size"] = round(brouillon["allocated_budget"] * 0.3, 2)
        session["etape"] = "valider"
        return {"etat": "en_cours", "etape": "valider",
                "reponse": _formater_recap(brouillon) +
                           "\n\nRéponds `valider` pour créer ce plan, ou `ajuster` pour modifier."}

    # Étape VALIDER
    if etape == "valider":
        m = message.strip().lower()
        if m in ("valider", "ok", "go", "oui"):
            try:
                pid = creer_plan(brouillon)
                return _terminer(session_id, pid)
            except Exception as e:
                logger.error(f"Création plan : {e}")
                return {"etat": "erreur", "reponse": f"❌ Erreur création : {e}"}
        if m in ("ajuster", "modifier", "non"):
            # On revient au début (simple — pas d'ajustement granulaire en V1)
            _nouveau_brouillon(session_id)
            return {"etat": "en_cours", "etape": "type",
                    "reponse": "OK, recommençons. Quel type de plan ?"}
        return {"etat": "en_cours", "etape": "valider",
                "reponse": "Réponds `valider` pour créer, ou `ajuster` pour modifier."}

    # Fallback
    return {"etat": "erreur", "reponse": "État de conversation inconnu — relance avec 'nouveau'."}


def _formater_recap(b: dict) -> str:
    return (
        f"📌 **Plan proposé** :\n"
        f"- Type : {b.get('plan_type')}\n"
        f"- Nom : {b.get('name')}\n"
        f"- Budget alloué : {b.get('allocated_budget', 0):.0f}€\n"
        f"- Objectif : +{b.get('target_return_percent', 0):.0f}% → {b.get('target_amount', 0):.0f}€\n"
        f"- Horizon : {b.get('time_horizon')}\n"
        f"- Vision : {b.get('vision', '')[:200]}\n"
        f"- Taille max/position : {b.get('max_position_size', 0):.0f}€"
    )
