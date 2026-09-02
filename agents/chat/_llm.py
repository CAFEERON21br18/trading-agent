"""
agents/chat/_llm.py — Couche LLM Gemini pour le chat stratégique (v5.3.4).
Le contexte structuré + le template (fallback) sont injectés dans le prompt.
Gemini synthétise une réponse naturelle. Si indisponible : on retombe sur
le template (comportement v5.3 inchangé).
"""

from utils.llm    import ask_llm
from utils.gemini import gemini_disponible


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
            if d.get("in_watchlist"):
                # v5.4.2 : actif suivi → décision + reasoning existants
                sections.append(f"{t} [suivi] : décision {d.get('decision')} "
                                f"(conf {d.get('confidence')}/10, score {d.get('score', 0):+.2f}) "
                                f"— {(d.get('reasoning') or '')[:250]}")
            elif d.get("found"):
                # v5.4.2 : actif hors watchlist → chiffres yfinance à la volée
                sections.append(
                    f"{t} [hors watchlist, yfinance] : "
                    f"prix {d.get('prix')}, RSI {d.get('rsi')}, "
                    f"SMA20 {d.get('sma20')}, SMA50 {d.get('sma50')}, "
                    f"perf 1 mois {d.get('change_1m_pct')}%. "
                    f"⚠️ Pas d'analyse Decision Engine — actif non suivi par l'agent."
                )
            else:
                sections.append(f"{t} : {d.get('note') or d.get('error') or 'données indisponibles'}")
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


MESSAGES_ERREUR_UI = {
    "quota_quotidien":   ("⚠️ **Service IA temporairement indisponible** — "
                          "le quota Gemini gratuit (20 req/jour) est épuisé. "
                          "Reset chaque jour. En attendant, voici les chiffres bruts du contexte :"),
    "rate_limit_minute": ("⚠️ **IA saturée** — trop de requêtes la minute écoulée. "
                          "Réessaie dans une trentaine de secondes. Chiffres bruts en attendant :"),
    "service_unavailable": ("⚠️ **Service Gemini en panne (503)** — momentanément indisponible côté Google. "
                            "Chiffres bruts :"),
    "clé_invalide":      ("❌ **Clé API Gemini invalide** — vérifie la valeur dans `.env`. "
                          "Chiffres bruts :"),
    "clé_manquante":     ("❌ **Clé API Gemini absente** — ajoute `GEMINI_API_KEY=…` dans `.env`. "
                          "Chiffres bruts :"),
    "réponse_vide":      ("⚠️ **L'IA n'a rien renvoyé** — réessaie ou reformule la question. "
                          "Chiffres bruts :"),
    "réseau":            ("⚠️ **Problème réseau vers Gemini** — réessaie dans un instant. "
                          "Chiffres bruts :"),
    # v5.4.0 — fallback Groq
    "clé_groq_manquante":("⚠️ **Quota Gemini épuisé et clé Groq absente** — ajoute "
                          "`GROQ_API_KEY=…` dans `.env` pour le fallback automatique. "
                          "Chiffres bruts :"),
    "clé_groq_invalide": ("⚠️ **Quota Gemini épuisé et clé Groq invalide** — vérifie "
                          "`GROQ_API_KEY` dans `.env` (la clé fournie a été rejetée par Groq). "
                          "Chiffres bruts :"),
    "rate_limit_groq":   ("⚠️ **IA saturée des deux côtés** — Gemini en quota et Groq en "
                          "rate-limit. Réessaie dans 1 min. Chiffres bruts :"),
    "both_failed":       ("⚠️ **Service IA temporairement indisponible** — Gemini en quota "
                          "et fallback Groq KO (voir les logs pour le détail). "
                          "Chiffres bruts du contexte :"),
    "inconnu":           ("⚠️ **Erreur IA inattendue** — voir les logs. Chiffres bruts :"),
}


def enrichir_avec_gemini(question: str, intention: str,
                         template_reponse: str, contexte: dict) -> tuple[str, str]:
    """
    Tente d'enrichir la réponse template via Gemini.
    Retourne (reponse_finale, source) où source ∈ {gemini, template, llm_indispo:<type>}.
    Si Gemini échoue, retourne une bannière d'erreur CLAIRE + le template
    (au lieu de retourner silencieusement le template comme avant).
    """
    if not gemini_disponible():
        banniere = MESSAGES_ERREUR_UI["clé_manquante"]
        return f"{banniere}\n\n{template_reponse}", "llm_indispo:clé_manquante"

    prompt = _construire_prompt(question, intention, template_reponse, contexte)
    res = ask_llm(prompt, system=SYSTEM_PROMPT, temperature=0.6,
                   max_tokens=900, mode="verbose")
    if res.get("text") and res.get("source") in ("gemini", "groq") and len(res["text"]) > 30:
        # Indique discrètement quand c'est Groq qui a répondu (fallback)
        suffixe = "\n\n_via Groq (fallback)_" if res["source"] == "groq" else ""
        return res["text"] + suffixe, res["source"]

    # Échec — bannière d'erreur claire + template comme fallback
    err_type = res.get("error") or "inconnu"
    # Map vers les bannières existantes (les nouveaux types Groq utilisent inconnu)
    banniere = MESSAGES_ERREUR_UI.get(err_type, MESSAGES_ERREUR_UI["inconnu"])
    retry = res.get("retry_after_sec")
    if retry:
        banniere = banniere.rstrip(":") + f" (retry possible dans ~{retry}s) :"
    return f"{banniere}\n\n{template_reponse}", f"llm_indispo:{err_type}"
