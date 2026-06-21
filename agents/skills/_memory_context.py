"""
agents/skills/_memory_context.py — Construit des contextes mémoire pour chaque skill.
Les skills restent agnostiques de la source ; ces helpers leur fournissent
des phrases factuelles à injecter dans le prompt.
"""

from utils.memory_lookups import (
    winrate_par_actif, winrate_recent, pertes_consecutives_recentes,
    setups_similaires, classifier_actif,
)


def contexte_bayesien(ticker: str, regime: str | None = None) -> dict:
    """Prior et facteurs pour le skill bayésien.
    Retourne {prior: 0..1, contexte_str: str}."""
    parts = []
    prior = 0.5

    wr_actif = winrate_par_actif(ticker)
    if wr_actif:
        prior = wr_actif["winrate_pct"] / 100
        parts.append(
            f"Historique sur {ticker} : {wr_actif['gagnants']}/{wr_actif['total']} "
            f"trades gagnants ({wr_actif['winrate_pct']:.0f}% winrate, "
            f"P&L moyen {wr_actif['avg_pnl']:+.2f}%)"
        )
    else:
        wr_global = winrate_recent(20)
        if wr_global:
            prior = wr_global["winrate_pct"] / 100
            parts.append(
                f"Pas d'historique propre à {ticker}. Fallback global : "
                f"{wr_global['winrate_pct']:.0f}% winrate sur "
                f"{wr_global['echantillon']} derniers trades"
            )

    if regime:
        parts.append(f"Régime de marché courant : {regime}")

    return {
        "prior":         max(0.05, min(0.95, prior)),
        "contexte_str":  "\n".join(parts) if parts else "(aucun historique)",
    }


def contexte_base_rates(ticker: str, direction: str) -> dict:
    """Classe de référence + taux historique pour le skill base_rates.
    Retourne {classe_ref: str, contexte_str: str}."""
    classe_actif = classifier_actif(ticker)
    similaires = setups_similaires(direction, asset_class=classe_actif, limit=30)

    if not similaires:
        return {
            "classe_ref":   f"{classe_actif} {direction.upper()}",
            "contexte_str": (f"Aucun historique de trades {direction.upper()} "
                              f"sur la classe {classe_actif}."),
        }

    pnls   = [s["pnl_pct"] for s in similaires]
    wins   = [p for p in pnls if p > 0]
    winrate = len(wins) / len(pnls) * 100
    avg_pnl = sum(pnls) / len(pnls)

    classe = f"trades {direction.upper()} sur {classe_actif} (n={len(similaires)})"
    contexte = (
        f"Classe de référence : {classe}\n"
        f"Winrate historique : {winrate:.0f}% ({len(wins)}/{len(pnls)})\n"
        f"P&L moyen : {avg_pnl:+.2f}%\n"
        f"Échantillon récent (top 5) : "
        + ", ".join(f"{s['ticker']} {s['pnl_pct']:+.1f}%" for s in similaires[:5])
    )
    return {"classe_ref": classe, "contexte_str": contexte}


def contexte_metacognition(decision_result: dict) -> dict:
    """Signaux comportementaux pour le skill métacognition.
    Détecte revenge-trading, sur-confiance, etc."""
    parts = []
    pertes = pertes_consecutives_recentes()
    if pertes >= 2:
        parts.append(
            f"⚠️ {pertes} pertes consécutives récentes — surveiller le biais "
            f"de revanche (revenge trading)"
        )

    conf = decision_result.get("confidence", 0)
    if conf >= 9:
        parts.append(
            f"Confiance auto-évaluée très élevée ({conf}/10) — surveiller "
            f"le biais de sur-confiance"
        )

    contras = decision_result.get("contradictions", [])
    if contras:
        parts.append(
            f"Contradictions ignorées dans la décision finale : "
            f"{len(contras)} signal(s) contraire(s) détecté(s)"
        )

    wr = winrate_recent(20)
    if wr and wr["winrate_pct"] < 35:
        parts.append(
            f"Performance récente faible ({wr['winrate_pct']:.0f}% winrate) — "
            f"pression à 'se refaire' possible"
        )

    return {"contexte_str": "\n".join(parts) if parts else
            "Aucun signal comportemental notable."}
