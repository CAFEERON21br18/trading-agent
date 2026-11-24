"""
agents/orchestrator_resume.py — Deux blocs de texte du rapport quotidien : le résumé
« 30 secondes » et le tableau de la watchlist.
Sorti de agents/orchestrator.py (règle des 200 lignes) ; orchestrator.py le réexporte.
"""


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
