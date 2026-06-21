"""
agents/chat/_llm.py — Couche LLM Gemini pour le chat stratégique (v5.3.4).
Le contexte structuré + le template (fallback) sont injectés dans le prompt.
Gemini synthétise une réponse naturelle. Si indisponible : on retombe sur
le template (comportement v5.3 inchangé).
"""

from utils.gemini import ask_gemini, gemini_disponible


SYSTEM_PROMPT = """Tu es AlphaSignal, un analyste quantitatif senior et gestionnaire de portefeuille.
Tu réponds à un utilisateur intermédiaire (pas débutant) qui fait du paper trading
sur la plateforme AlphaSignal et tient aussi un portefeuille réel sur Revolut.

RÈGLES STRICTES :
1. RÉPONDS EN FRANÇAIS. Style direct, sans bla-bla. Pédagogique mais pas basique.
2. UTILISE EXCLUSIVEMENT les chiffres du contexte fourni. N'invente JAMAIS de
   prix, P&L, signaux, news ou décisions. Si un chiffre manque, dis-le.
3. PAPER TRADING UNIQUEMENT — l'utilisateur ne passe aucun ordre via toi.
   Pour les positions réelles, tu CONSEILLES, tu n'exécutes rien.
4. Termine TOUJOURS par un disclaimer court si la réponse contient une
   décision/recommandation : "⚠️ Pas un conseil financier — paper trading."
5. Si la question dépasse le contexte fourni, dis-le honnêtement plutôt
   que d'inventer.
6. Sois CONCIS. Réponse cible : 4 à 12 lignes max sauf si la question
   exige du détail technique.
7. Tu peux légèrement t'écarter des indicateurs si tu reconnais un pattern
   en mémoire — mentionne-le.
8. Cite les noms d'actifs en tickers (BTC-USD, AAPL, etc.).
"""


def _construire_prompt(question: str, intention: str,
                       template_reponse: str, contexte: dict) -> str:
    """Assemble le prompt utilisateur : contexte + question."""
    sections = [f"INTENTION DÉTECTÉE : {intention}", ""]

    paper = contexte.get("paper_portfolio") or {}
    if paper:
        sections.append("== PAPER PORTFOLIO ==")
        sections.append(f"Capital : {paper.get('capital_total', 0):.2f}€ | "
                        f"Investi : {paper.get('invested', 0):.2f}€ | "
                        f"Cash : {paper.get('cash', 0):.2f}€")
        sections.append(f"Positions : {paper.get('open_positions_count', 0)}/"
                        f"{paper.get('max_positions', 20)} | "
                        f"P&L latent : {paper.get('unrealized_pnl', 0):+.2f}€")
        sections.append(f"Mode : {'défensif' if paper.get('mode_defensif') else 'normal'}")
        sections.append("")

    perf = contexte.get("performance") or {}
    if perf and perf.get("nb_trades"):
        sections.append(f"Performance (20 derniers trades) : "
                        f"winrate {perf.get('win_rate', 0):.0f}%, "
                        f"profit factor {perf.get('profit_factor', 0):.2f}")
        sections.append("")

    real = contexte.get("real_resume") or {}
    if real and real.get("open_count"):
        sections.append("== PORTEFEUILLE RÉEL ==")
        sections.append(f"{real.get('open_count', 0)} positions ouvertes, "
                        f"investi {real.get('total_invested', 0):.2f}€, "
                        f"P&L réalisé {real.get('realized_pnl', 0):+.2f}€")
        for i in (contexte.get("real_open") or [])[:5]:
            sections.append(f"  {i['asset']} : qty {i['quantity']:.4f}, "
                            f"entrée {i['entry_price']:.2f}€, "
                            f"{i['holding_type']}/{i['instrument_type']}")
        sections.append("")

    asset_data = contexte.get("asset_data") or {}
    if asset_data:
        sections.append("== ANALYSE ACTIFS ==")
        for t, d in list(asset_data.items())[:3]:
            sections.append(f"{t} : décision {d.get('decision')} "
                            f"(conf {d.get('confidence')}/10, score {d.get('score', 0):+.2f}) "
                            f"— {(d.get('reasoning') or '')[:250]}")
        sections.append("")

    market = contexte.get("market_context") or {}
    if market.get("valeur") is not None:
        sections.append(f"Fear & Greed : {market.get('valeur')} ({market.get('label')})")
        sections.append("")

    knowledge = contexte.get("knowledge") or []
    if knowledge:
        sections.append("== CONCEPTS THÉORIQUES MOBILISÉS ==")
        for c in knowledge:
            sections.append(f"[{c['domaine']}] {c['concept']} : {c['definition'][:300]}")
        sections.append("")

    # Le template est inclus comme "draft" — Gemini peut s'en inspirer
    sections.append("== BROUILLON STRUCTURÉ (résume les faits, à reformuler en mieux) ==")
    sections.append(template_reponse)
    sections.append("")

    sections.append(f"== QUESTION DE L'UTILISATEUR ==")
    sections.append(question)
    sections.append("")
    sections.append("Ta réponse (4-12 lignes, française, basée UNIQUEMENT sur les faits ci-dessus) :")
    return "\n".join(sections)


def enrichir_avec_gemini(question: str, intention: str,
                         template_reponse: str, contexte: dict) -> tuple[str, str]:
    """
    Tente d'enrichir la réponse template via Gemini.
    Retourne (reponse_finale, source) où source ∈ {gemini, template, template_fallback}.
    """
    if not gemini_disponible():
        return template_reponse, "template"
    prompt = _construire_prompt(question, intention, template_reponse, contexte)
    llm_text = ask_gemini(prompt, system=SYSTEM_PROMPT, temperature=0.6,
                          max_output_tokens=900)
    if llm_text and len(llm_text) > 30:
        return llm_text, "gemini"
    return template_reponse, "template_fallback"
