"""
agents/analysts/risk_manager/rapport.py — Rapport texte du Risk Manager.
Sorti de manager.py (règle des 200 lignes) ; manager.py le réexporte.
"""

from datetime import datetime, timezone

import config


def formater_rapport_risque(resultat: dict) -> str:
    """Génère le rapport texte."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sep = "─" * 60
    entete = f"ANALYSE RISQUE — {now}\n{sep}"

    if not resultat["valide"]:
        rejets = "\n".join(f"  • {r}" for r in resultat["rejets"])
        return f"{entete}\n❌ SIGNAL REJETÉ\n\n{rejets}"

    s = resultat["signal"]
    rapport = (
        f"{entete}\n"
        f"Actif                : {s['ticker']}\n"
        f"Direction            : {s['direction']}\n"
        f"Capital total        : {config.CAPITAL:.2f}€\n"
        f"Capital investissable: {s['capital_investissable']:.2f}€ ({config.MAX_CAPITAL_INVESTI_PCT:.0f}%)\n"
        f"Cash réserve         : {config.CASH_RESERVE:.2f}€ (intouchable)\n"
        f"Budget alloué        : {s['budget_par_position']:.2f}€\n"
        f"Risque max théorique : {config.RISK_PER_TRADE_PCT:.1f}% = {s['montant_risque_theorique']:.2f}€\n"
        f"Risque RÉEL          : {s['montant_risque_reel']:.2f}€\n"
        f"Limite active        : {s['limite_active']}\n{sep}\n"
        f"Prix d'entrée        : {s['prix_entree']:,.4f}\n"
        f"Stop-loss            : {s['stop_loss']:,.4f} (ATR {s['atr']:.4f}, support {s.get('support_utilise')})\n"
        f"Target 1             : {s['target_1']:,.4f} (R:R 1:{s['rr_1']:.2f})\n"
        f"Target 2             : {s['target_2']:,.4f} (R:R 1:{s['rr_2']:.2f})\n{sep}\n"
        f"Taille position      : {s['taille_unites']:.6f} unités\n"
        f"Montant investi      : {s['montant_investi']:.2f}€\n{sep}\n"
        "✅ SIGNAL VALIDÉ — Exécution MANUELLE sur Revolut.\n"
        "⚠️  Disclaimer : analyse à titre informatif. Décision finale = utilisateur."
    )
    if resultat["avertissements"]:
        avert = "\n".join(f"  • {a}" for a in resultat["avertissements"])
        rapport += f"\n{sep}\n⚠️  Avertissements :\n{avert}"
    return rapport
