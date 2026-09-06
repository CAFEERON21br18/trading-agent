"""
agents/technical_skills/setup_quality.py — Skill 3 : score de qualité d'un setup.

Note la CONFLUENCE des facteurs favorables (8 critères binaires) et attribue
un grade A+/A/B/C/D. Complémentaire du Budget Manager (qui note la confiance
brute) : ici on récompense l'alignement de plusieurs sources.

Python pur, aucun LLM. Aucune BDD (le grade est joint à la décision).
"""

# Grade → seuil de critères remplis (v5.5.5 : sur 9 critères désormais)
GRADES = [
    ("A+", 8),
    ("A",  7),
    ("B",  5),
    ("C",  3),
    ("D",  0),
]

# Facteur d'ajustement Budget Manager : bonus si beau setup, malus si mauvais
BUDGET_BOOST = {"A+": 1.5, "A": 1.2, "B": 1.0, "C": 0.5, "D": 0.0}


def _direction_bullish(analyse: dict) -> int:
    """+1 haussier, -1 baissier, 0 neutre."""
    d = (analyse or {}).get("direction", "").upper()
    if d in ("ACHAT", "BULLISH", "POSITIF", "LONG"): return 1
    if d in ("VENTE", "BEARISH", "NEGATIF", "NÉGATIF", "SHORT"): return -1
    return 0


def _decision_bullish(decision: str) -> int:
    """+1 BUY, -1 SELL, 0 HOLD/NO_TRADE."""
    if decision == "BUY":  return 1
    if decision == "SELL": return -1
    return 0


def noter_setup(analyses: dict, decision_result: dict) -> dict:
    """Note un setup selon 8 critères. Retourne
    {grade, score, criteres, criteres_ok, criteres_manquants, budget_boost}."""
    d_dir = _decision_bullish(decision_result.get("decision", ""))
    criteres = {}

    # 1. Signal technique fort (confiance ≥ 7)
    tech = analyses.get("technique") or {}
    criteres["signal_technique_fort"] = bool(tech.get("confiance", 0) >= 7)

    # 2. Régime marché aligné avec direction
    regime = (analyses.get("context") or {}).get("regime_marche")
    if regime in ("haussier", "baissier") and d_dir != 0:
        aligne = (regime == "haussier" and d_dir > 0) or (regime == "baissier" and d_dir < 0)
        criteres["regime_aligne"] = aligne
    else:
        criteres["regime_aligne"] = False

    # 3. Fondamental aligné
    fonda_dir = _direction_bullish(analyses.get("fondamental"))
    criteres["fondamental_aligne"] = (fonda_dir != 0 and fonda_dir == d_dir)

    # 4. Sentiment aligné
    sent_dir = _direction_bullish(analyses.get("sentiment"))
    criteres["sentiment_aligne"] = (sent_dir != 0 and sent_dir == d_dir)

    # 5. ≥ 2 convergences sous-agents
    convs = decision_result.get("convergences") or []
    criteres["convergences_multiples"] = len(convs) >= 2

    # 6. Pas de contradiction majeure
    contras = decision_result.get("contradictions") or []
    criteres["sans_contradiction"] = len(contras) == 0

    # 7. Pas d'override Risk
    overrides = decision_result.get("overrides") or []
    criteres["sans_override"] = len(overrides) == 0

    # 8. R:R ≥ 1.5 sur le signal
    risque = analyses.get("risque") or {}
    signal = risque.get("signal") or {}
    rr_1 = signal.get("rr_1") if isinstance(signal, dict) else None
    criteres["rr_favorable"] = bool(rr_1 and rr_1 >= 1.5)

    # 9. v5.5.5 — Liquidité suffisante (Skill 6)
    ticker = decision_result.get("ticker")
    if ticker:
        try:
            from agents.technical_skills.liquidity import liquidite_suffisante
            criteres["liquidite_ok"] = bool(liquidite_suffisante(ticker))
        except Exception:
            criteres["liquidite_ok"] = True  # bénéfice du doute
    else:
        criteres["liquidite_ok"] = True

    score = sum(1 for v in criteres.values() if v)

    # Grade
    grade = "D"
    for g, seuil in GRADES:
        if score >= seuil:
            grade = g
            break

    ok = [k for k, v in criteres.items() if v]
    ko = [k for k, v in criteres.items() if not v]
    return {
        "grade":               grade,
        "score":               score,
        "total_criteres":      len(criteres),
        "criteres":            criteres,
        "criteres_ok":         ok,
        "criteres_manquants":  ko,
        "budget_boost":        BUDGET_BOOST.get(grade, 1.0),
    }


def grade_emoji(grade: str) -> str:
    """Emoji visuel pour rapport / dashboard."""
    return {"A+": "🌟", "A": "✅", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")
