"""
agents/chat/_formatters.py — Formatters templates pour le chat (fallback Gemini).
Ces fonctions transforment le contexte structuré en texte lisible.
Servent à la fois de fallback (si Gemini indispo) et de matière première
au prompt LLM.
TODO §8 : une valeur inconnue s'affiche « non disponible », jamais 0.
"""

from agents.chat._pnl_latent import NON_DISPO, nd, texte_pnl


def _eur(v) -> str:
    if v is None:
        return NON_DISPO
    return f"{v:+.2f}€" if isinstance(v, (int, float)) else str(v)


def formater_paper_status(ctx: dict) -> str:
    p    = ctx.get("paper_portfolio", {})
    perf = ctx.get("performance", {})
    if not p:
        return "Aucune donnée paper portfolio disponible pour le moment."
    lignes = [
        f"📊 **Paper trading** :",
        f"- Capital total : {p.get('capital_total', 0):.2f}€",
        f"- Investi : {p.get('invested', 0):.2f}€ | Cash : {p.get('cash', 0):.2f}€",
        f"- Positions ouvertes : {p.get('open_positions_count', 0)}/{p.get('max_positions', 20)}",
        f"- P&L latent : {texte_pnl(ctx.get('pnl_latent'))}",
    ]
    if perf and perf.get("nb_trades"):
        lignes.append(f"- {perf['nb_trades']} derniers trades avec résultat (20 au plus) : "
                      f"winrate {perf.get('win_rate', 0):.0f}%, profit factor {perf.get('profit_factor', 0):.2f}")
    lignes.append(f"- Mode : {'défensif' if p.get('mode_defensif') else 'NORMAL'}")
    return "\n".join(lignes)


def formater_real_status(ctx: dict) -> str:
    r    = ctx.get("real_resume", {})
    invs = ctx.get("real_open", [])
    if not r or not r.get("open_count"):
        return ("💰 **Portefeuille réel** : aucune position enregistrée. "
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
        lignes.append(f"\n🔔 **{len(advice)} conseil(s) en attente** — va sur la page Réel.")
    return "\n".join(lignes)


def _sans_decision(data: dict) -> str:
    """Pas de décision ≠ signal neutre (TODO §8)."""
    if data.get("in_watchlist") is False:
        return "  Analyse du Decision Engine non disponible : actif hors watchlist."
    return "  Analyse technique non disponible (calcul en échec ou données manquantes)."


def formater_advice_sell(ctx: dict) -> str:
    tickers = ctx.get("tickers_mentionnes", [])
    if not tickers:
        return ("Tu me demandes de vendre — sur quel actif précisément ? "
                "Précise un ticker (ex: AAPL, BTC, NVDA) et je te donne mon avis.")
    rep = []
    for t in tickers[:2]:
        data = ctx.get("asset_data", {}).get(t, {})
        rep.append(f"**{t}** :")
        if not data.get("decision"):
            rep.append(_sans_decision(data))
        elif data.get("decision") == "SELL":
            rep.append(f"  ✓ Signal SELL (score {nd(data.get('score'), '{:+.2f}')}, "
                       f"conf {nd(data.get('confidence'), '{}/10')})")
            rep.append(f"  Raison : {data.get('reasoning', '')[:200]}")
        elif data.get("decision") == "BUY":
            rep.append(f"  ⚠️ Au contraire signal BUY (conf {data.get('confidence')}/10). "
                       f"Vendre maintenant irait contre l'analyse technique.")
        else:
            rep.append(f"  Signal neutre. Vendre pour des raisons hors-technique reste valable.")
    rep.append("\n💡 R:R : couper les pertes vite, laisser courir les gains.")
    return "\n".join(rep)


def formater_advice_buy(ctx: dict) -> str:
    tickers = ctx.get("tickers_mentionnes", [])
    if not tickers:
        return "Sur quel actif veux-tu un avis d'achat ? Précise un ticker."
    rep = []
    for t in tickers[:2]:
        data = ctx.get("asset_data", {}).get(t, {})
        rep.append(f"**{t}** :")
        if not data.get("decision"):
            rep.append(_sans_decision(data))
        elif data.get("decision") == "BUY":
            rep.append(f"  ✓ Signal BUY (score {nd(data.get('score'), '{:+.2f}')}, "
                       f"conf {nd(data.get('confidence'), '{}/10')})")
            rep.append(f"  Raison : {data.get('reasoning', '')[:200]}")
        elif data.get("decision") == "SELL":
            rep.append(f"  ⚠️ Signal SELL (conf {data.get('confidence')}/10). Acheter ici = contre tendance.")
        else:
            rep.append(f"  Signal neutre. Pas d'avantage technique clair.")
    return "\n".join(rep)


def formater_market_crypto(ctx: dict) -> str:
    fg = ctx.get("market_context", {})
    fg_val = fg.get("valeur")
    rep = [f"📈 **Marché crypto** :"]
    if fg_val is not None:
        rep.append(f"- Fear & Greed : {fg_val} ({fg.get('label', '?')})")
        if fg_val < 25:
            rep.append("  → Zone d'accumulation (Extreme Fear). 'Be greedy when others are fearful'.")
        elif fg_val > 75:
            rep.append("  → Prudence (Extreme Greed). Profits partiels à considérer.")
        else:
            rep.append("  → Neutre. Suivre les setups techniques sans biais émotionnel.")
    btc = ctx.get("asset_data", {}).get("BTC-USD", {})
    if btc:
        rep.append(f"\n**BTC** : {btc.get('decision')} (conf {btc.get('confidence')}/10) — "
                   f"{btc.get('reasoning', '')[:150]}")
    rep.append("\n⚠️ Je ne prédis pas l'avenir. Je présente le contexte ; à toi de décider.")
    return "\n".join(rep)


def formater_theorie(ctx: dict) -> str:
    concepts = ctx.get("knowledge", [])
    if not concepts:
        return "Pas de concept précis trouvé dans ma base. Reformule plus précisément."
    rep = ["📚 **Base de connaissances** :"]
    for c in concepts:
        rep.append(f"\n**[{c['domaine']}] {c['concept'].replace('_', ' ')}** :\n{c['definition']}")
    return "\n".join(rep)


def formater_par_intention(intention: str, ctx: dict) -> str:
    """Aiguillage central — retourne le texte template selon l'intention."""
    if intention == "paper_status":
        return formater_paper_status(ctx)
    if intention == "real_status":
        return formater_real_status(ctx)
    if intention == "advice_sell":
        return formater_advice_sell(ctx)
    if intention == "advice_buy":
        return formater_advice_buy(ctx)
    if intention == "market_crypto":
        return formater_market_crypto(ctx)
    if intention in ("theory_risk", "theory_macro"):
        return formater_theorie(ctx)
    # Général : un mix paper + réel + knowledge si dispo
    parts = []
    if ctx.get("tickers_mentionnes"):
        parts.append(formater_advice_buy(ctx))
    else:
        parts.append(formater_paper_status(ctx))
        if ctx.get("real_resume", {}).get("open_count"):
            parts.append("\n" + formater_real_status(ctx))
    if ctx.get("knowledge"):
        parts.append("\n" + formater_theorie(ctx))
    return "\n".join(parts)
