"""
agents/chat/chat_engine.py — Moteur du chat stratégique (v5.0)
V1 : routage par intention + génération basée sur contexte structuré.
Pas de LLM externe nécessaire. À l'avenir : brancher Anthropic API
si CLAUDE_API_KEY est défini dans .env.
"""

import sys
import os
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger
from utils.database import get_connection
from agents.chat.context_builder import build_context

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialiser_chat_db() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            context_used TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _detecter_intention(question: str) -> str:
    """Classifie la question pour router la réponse."""
    q = question.lower()
    if any(k in q for k in ["paper", "papier", "comment se porte", "performance"]):
        return "paper_status"
    if any(k in q for k in ["réel", "réelle", "real", "mon portefeuille", "mes positions réelles"]):
        return "real_status"
    if any(k in q for k in ["vendre", "vends", "sortir", "fermer", "couper"]):
        return "advice_sell"
    if any(k in q for k in ["acheter", "achète", "renforcer", "entrer", "investir"]):
        return "advice_buy"
    if any(k in q for k in ["pourquoi tu as", "explique"]):
        return "explain"
    if any(k in q for k in ["stratégie", "plan", "thèse", "opportun"]):
        return "strategy"
    if any(k in q for k in ["risque", "r:r", "ratio", "kelly", "drawdown"]):
        return "theory_risk"
    if any(k in q for k in ["macro", "économie", "fed", "taux", "récession"]):
        return "theory_macro"
    if any(k in q for k in ["btc", "bitcoin", "crypto", "marché crypto"]):
        return "market_crypto"
    return "general"


def _eur(v) -> str:
    if v is None: return "—"
    return f"{v:+.2f}€" if isinstance(v, (int, float)) else str(v)


def _formater_paper_status(ctx: dict) -> str:
    p = ctx.get("paper_portfolio", {})
    perf = ctx.get("performance", {})
    if not p:
        return "Aucune donnée paper portfolio disponible pour le moment."
    lignes = [
        f"📊 **Paper trading** :",
        f"- Capital total : {p.get('capital_total', 0):.2f}€",
        f"- Investi : {p.get('invested', 0):.2f}€ | Cash : {p.get('cash', 0):.2f}€",
        f"- Positions ouvertes : {p.get('open_positions_count', 0)}/{p.get('max_positions', 20)}",
        f"- P&L latent : {_eur(p.get('unrealized_pnl'))}",
    ]
    if perf and perf.get("nb_trades"):
        lignes.append(f"- Sur les 20 derniers trades : winrate {perf.get('win_rate', 0):.0f}%, "
                      f"profit factor {perf.get('profit_factor', 0):.2f}")
    lignes.append(f"- Mode : {'défensif' if p.get('mode_defensif') else 'NORMAL'}")
    return "\n".join(lignes)


def _formater_real_status(ctx: dict) -> str:
    r = ctx.get("real_resume", {})
    invs = ctx.get("real_open", [])
    if not r or not r.get("open_count"):
        return ("💰 **Portefeuille réel** : tu n'as aucune position enregistrée. "
                "Va sur la page 'Portefeuille Réel' pour ajouter tes positions Revolut.")
    lignes = [
        f"💰 **Portefeuille réel** :",
        f"- {r.get('open_count', 0)} positions ouvertes",
        f"- Total investi : {r.get('total_invested', 0):.2f}€",
        f"- P&L réalisé (positions closes) : {_eur(r.get('realized_pnl'))}",
    ]
    if invs:
        lignes.append("\nPositions actuelles :")
        for i in invs[:10]:
            lignes.append(f"  • {i['asset']} ({i['holding_type']}/{i['instrument_type']}) — "
                          f"{i['quantity']:.6f}u entré à {i['entry_price']:.4f}")
    advice = ctx.get("real_advice", [])
    if advice:
        lignes.append(f"\n🔔 **{len(advice)} conseil(s) en attente** — va sur la page Réel pour répondre.")
    return "\n".join(lignes)


def _formater_advice_sell(ctx: dict) -> str:
    tickers = ctx.get("tickers_mentionnes", [])
    if not tickers:
        return ("Tu me demandes de vendre — sur quel actif précisément ? "
                "Précise un ticker (ex: AAPL, BTC, NVDA) et je te donne mon avis basé sur "
                "tes positions et l'analyse actuelle.")
    rep = []
    for t in tickers[:2]:
        data = ctx.get("asset_data", {}).get(t, {})
        rep.append(f"**{t}** :")
        if data.get("decision") == "SELL":
            rep.append(f"  ✓ L'agent voit aussi un signal SELL (score {data.get('score', 0):+.2f}, conf {data.get('confidence')}/10)")
            rep.append(f"  Raison : {data.get('reasoning', '')[:200]}")
        elif data.get("decision") == "BUY":
            rep.append(f"  ⚠️ L'agent voit au contraire un signal BUY (conf {data.get('confidence')}/10). "
                       f"Vendre maintenant irait contre l'analyse technique.")
        else:
            rep.append(f"  Signal neutre actuellement. Si tu veux vendre c'est pour des raisons hors-technique "
                       f"(prise de profit, besoin de cash, etc.) — ça reste valable.")
    rep.append("\n💡 Rappel R:R (knowledge base) : couper les pertes vite, laisser courir les gains.")
    return "\n".join(rep)


def _formater_advice_buy(ctx: dict) -> str:
    tickers = ctx.get("tickers_mentionnes", [])
    if not tickers:
        return "Sur quel actif veux-tu un avis d'achat ? Précise un ticker."
    rep = []
    for t in tickers[:2]:
        data = ctx.get("asset_data", {}).get(t, {})
        rep.append(f"**{t}** :")
        if data.get("decision") == "BUY":
            rep.append(f"  ✓ L'agent voit un signal BUY (score {data.get('score', 0):+.2f}, conf {data.get('confidence')}/10)")
            rep.append(f"  Raison : {data.get('reasoning', '')[:200]}")
        elif data.get("decision") == "SELL":
            rep.append(f"  ⚠️ L'agent voit un signal SELL (conf {data.get('confidence')}/10). Acheter ici serait contre la tendance.")
        else:
            rep.append(f"  Signal neutre. Pas d'avantage technique clair.")
    return "\n".join(rep)


def _formater_market_crypto(ctx: dict) -> str:
    fg = ctx.get("market_context", {})
    fg_val = fg.get("valeur")
    fg_label = fg.get("label", "?")
    rep = [f"📈 **Marché crypto** :"]
    if fg_val is not None:
        rep.append(f"- Fear & Greed : {fg_val} ({fg_label})")
        if fg_val < 25:
            rep.append("  → Zone d'accumulation potentielle (Extreme Fear). Buffett : 'be greedy when others are fearful'.")
        elif fg_val > 75:
            rep.append("  → Prudence (Extreme Greed). Profits partiels à considérer.")
        else:
            rep.append("  → Neutre. Suivre les setups techniques sans biais émotionnel.")
    btc_data = ctx.get("asset_data", {}).get("BTC-USD", {})
    if btc_data:
        rep.append(f"\n**BTC** : décision actuelle {btc_data.get('decision')} "
                   f"(conf {btc_data.get('confidence')}/10) — {btc_data.get('reasoning', '')[:150]}")
    rep.append("\n⚠️ Je ne prédis pas l'avenir. Je présente le contexte actuel ; à toi de décider.")
    return "\n".join(rep)


def _formater_theorie(ctx: dict) -> str:
    concepts = ctx.get("knowledge", [])
    if not concepts:
        return "Je n'ai pas trouvé de concept précis dans ma base de connaissances. Reformule plus précisément."
    rep = ["📚 **De ma base de connaissances** :"]
    for c in concepts:
        rep.append(f"\n**[{c['domaine']}] {c['concept'].replace('_', ' ')}** :\n{c['definition']}")
    return "\n".join(rep)


def repondre(question: str) -> dict:
    """Génère une réponse à partir de la question + contexte."""
    initialiser_chat_db()
    intention = _detecter_intention(question)
    contexte = build_context(question)

    if intention == "paper_status":
        reponse = _formater_paper_status(contexte)
    elif intention == "real_status":
        reponse = _formater_real_status(contexte)
    elif intention == "advice_sell":
        reponse = _formater_advice_sell(contexte)
    elif intention == "advice_buy":
        reponse = _formater_advice_buy(contexte)
    elif intention == "market_crypto":
        reponse = _formater_market_crypto(contexte)
    elif intention in ("theory_risk", "theory_macro"):
        reponse = _formater_theorie(contexte)
    else:
        # Fallback général : un peu de tout selon ce qu'on a
        parts = []
        if contexte.get("tickers_mentionnes"):
            parts.append(_formater_advice_buy(contexte))
        else:
            parts.append(_formater_paper_status(contexte))
            if contexte.get("real_resume", {}).get("open_count"):
                parts.append("\n" + _formater_real_status(contexte))
        if contexte.get("knowledge"):
            parts.append("\n" + _formater_theorie(contexte))
        reponse = "\n".join(parts)

    # Enregistrer dans l'historique
    try:
        conn = get_connection()
        conn.execute("INSERT INTO chat_history (role, message) VALUES (?, ?)",
                     ("user", question))
        conn.execute("INSERT INTO chat_history (role, message) VALUES (?, ?)",
                     ("assistant", reponse))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Sauvegarde chat : {e}")

    return {"intention": intention, "reponse": reponse, "timestamp": _now()}


def historique(limite: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


def vider_historique() -> bool:
    conn = get_connection()
    conn.execute("DELETE FROM chat_history")
    conn.commit()
    conn.close()
    return True
