"""
agents/real_advisor_rules.py — Règles de génération des conseils sur le
portefeuille réel (v5.4.1). Toutes basées sur des règles déterministes :
fonctionnent SANS LLM (le LLM ne fait qu'enrichir le wording après).
Le real_advisor orchestre + appelle l'analyse technique + le LLM.
"""


def regles_position(inv: dict, inv_e: dict, plan: dict | None) -> list[dict]:
    """Génère les conseils par règles pures. Retourne une liste de dicts."""
    conseils = []
    prix    = inv_e["prix_actuel"]
    pnl_pct = inv_e["pnl_pct"]
    pnl_eur = inv_e["pnl_eur"]
    target  = inv["target_price"]
    sl      = inv["stop_loss_mental"]

    plan_type      = (plan or {}).get("plan_type", "")
    plan_name      = (plan or {}).get("name", "")
    plan_objective = (plan or {}).get("objective", "") or ""
    plan_vision    = (plan or {}).get("vision", "") or ""
    is_long_terme  = plan_type == "long_terme"
    is_court_terme = plan_type == "court_terme"

    # 1. Cible atteinte
    if target and inv["direction"] == "LONG" and prix >= target * 0.97:
        conseils.append({
            "advice_type": "ALERTE", "urgency": "haute",
            "recommendation": "prendre profit partiel",
            "reasoning": (f"{inv['asset']} approche ta cible {target:.2f} "
                          f"(actuel {prix:.2f}, +{pnl_pct:.1f}%). Envisage de prendre 50% "
                          f"de profit, laisser courir le reste."),
        })

    # 2. Stop mental violé
    if sl and inv["direction"] == "LONG" and prix <= sl:
        conseils.append({
            "advice_type": "ALERTE", "urgency": "haute",
            "recommendation": "vendre / couper",
            "reasoning": (f"{inv['asset']} a passé ton stop mental {sl:.2f} "
                          f"(actuel {prix:.2f}, {pnl_pct:.1f}%). Ta thèse est-elle "
                          f"invalidée ? Si oui, couper proprement."),
        })

    # 3. Perte importante (>15%) — adapté au plan
    if pnl_pct < -15:
        if is_long_terme and pnl_pct > -25:
            reco = "garder & vérifier la thèse"
            rsn  = (f"{inv['asset']} à {pnl_pct:.1f}% ({pnl_eur:+.2f}€). Plan "
                     f"« {plan_name} » : "
                     f"{plan_vision[:120] if plan_vision else plan_objective[:120]}. "
                     f"Pas de panique sur la volatilité — vérifier si la thèse de fond tient.")
            urg = "moyenne"
        elif is_court_terme:
            reco = "couper rapidement"
            rsn  = (f"{inv['asset']} à {pnl_pct:.1f}%. Plan court terme = discipline "
                     f"stop-loss stricte. Couper et redéployer.")
            urg = "haute"
        else:
            reco = "réévaluer la thèse"
            rsn  = (f"{inv['asset']} en perte de {pnl_pct:.1f}% ({pnl_eur:+.2f}€). "
                     f"Thèse initiale : '{inv.get('investment_thesis') or 'non documentée'}'. "
                     f"Reste-t-elle valable ? Sinon, coupe et redéploie.")
            urg = "moyenne"
        conseils.append({"advice_type": "CONSEIL", "recommendation": reco,
                          "reasoning": rsn, "urgency": urg})

    # 5. Gros gain (≥30%) sans cible définie
    elif pnl_pct >= 30 and not target:
        if is_long_terme:
            reco = "garder — laisser courir"
            rsn  = (f"{inv['asset']} à +{pnl_pct:.1f}% ({pnl_eur:+.2f}€). "
                     f"Plan « {plan_name} » : laisser courir les gagnants. "
                     f"Penser à définir une cible chiffrée pour l'étape suivante.")
        else:
            reco = "sécuriser une partie"
            rsn  = (f"{inv['asset']} à +{pnl_pct:.1f}% ({pnl_eur:+.2f}€). Penser à "
                     f"prendre 30-50% de profit pour sécuriser ; laisser le reste courir.")
        conseils.append({"advice_type": "CONSEIL", "recommendation": reco,
                          "reasoning": rsn, "urgency": "moyenne"})

    # 6. Gain modeste (5-30%)
    elif 5 <= pnl_pct < 30:
        plan_ctx = (f" Aligné avec « {plan_name} » : {plan_objective[:80]}." if plan else "")
        conseils.append({
            "advice_type": "INFO", "recommendation": "garder",
            "reasoning": (f"{inv['asset']} à +{pnl_pct:.1f}% ({pnl_eur:+.2f}€). "
                          f"Tendance positive, pas d'action requise.{plan_ctx}"),
            "urgency": "basse",
        })

    # 7. Position stable (-5% à +5%)
    elif -5 <= pnl_pct <= 5:
        plan_ctx = (f" Cohérent avec « {plan_name} »." if plan else "")
        conseils.append({
            "advice_type": "INFO", "recommendation": "garder",
            "reasoning": (f"{inv['asset']} stable ({pnl_pct:+.1f}%, "
                          f"{pnl_eur:+.2f}€).{plan_ctx}"),
            "urgency": "basse",
        })

    # 8. Légère perte (-5% à -15%) — pas critique
    elif -15 < pnl_pct < -5:
        if is_long_terme:
            rsn = (f"{inv['asset']} à {pnl_pct:.1f}%. Plan long terme « {plan_name} » : "
                    f"la volatilité courte ne change pas la thèse. Garder.")
        else:
            rsn = (f"{inv['asset']} à {pnl_pct:.1f}%. Surveiller — pas encore au seuil "
                    f"de coupe mais préparer un stop mental si la baisse continue.")
        conseils.append({"advice_type": "INFO", "recommendation": "surveiller",
                          "reasoning": rsn, "urgency": "basse"})

    return conseils


def regle_signal_technique(inv: dict, decision: dict, plan: dict | None) -> dict | None:
    """Règle 4 : signal SELL technique fort sur LONG → conseil cohérent au plan."""
    if (inv["direction"] != "LONG"
            or decision["decision"] != "SELL"
            or decision["confidence"] < 7):
        return None
    plan_type = (plan or {}).get("plan_type", "")
    plan_name = (plan or {}).get("name", "")
    if plan_type == "long_terme":
        return {
            "advice_type": "CONSEIL", "recommendation": "envisager fermeture",
            "reasoning": (f"Signal SELL technique sur {inv['asset']} "
                          f"(conf {decision['confidence']}/10) : "
                          f"{decision['reasoning'][:160]}. MAIS plan « {plan_name} » "
                          f"prévoit de garder. À vérifier seulement si la thèse de fond "
                          f"est invalidée."),
            "urgency": "basse",
        }
    return {
        "advice_type": "CONSEIL", "recommendation": "envisager fermeture",
        "reasoning": (f"L'agent détecte un signal SELL fort sur {inv['asset']} "
                      f"(conf {decision['confidence']}/10) : "
                      f"{decision['reasoning'][:200]}"),
        "urgency": "moyenne",
    }
