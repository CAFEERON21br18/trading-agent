"""
scripts/cycle_weekly.py — Cycle HEBDOMADAIRE (dimanche 20h)
Revue de la semaine + rapport hebdomadaire par email.
"""

import sys
import os
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.lock_manager import acquerir_lock, liberer_lock, doit_skipper
from utils.heartbeat import update_heartbeat

logger = get_logger("cycle_weekly")
CYCLE = "weekly"


def _generer_rapport_hebdo() -> str:
    """Génère le contenu markdown du rapport hebdomadaire."""
    from utils.portfolio_db import lire_positions_recentes_fermees, lire_dernier_snapshot
    from agents.paper_trader.portfolio import etat_portefeuille
    from agents.budget_manager.manager import tableau_de_bord
    from agents.trade_journalist.intuition_tracker import stats_intuition

    now = datetime.now(timezone.utc)
    annee, semaine, _ = now.isocalendar()
    fermees = lire_positions_recentes_fermees(limite=50)
    cette_sem = []
    for p in fermees:
        try:
            d = datetime.fromisoformat(p["exit_date"])
            jours = (now - d).days
            if jours <= 7:
                cette_sem.append(p)
        except Exception:
            pass

    nb = len(cette_sem)
    wins = sum(1 for p in cette_sem if (p.get("pnl_euros") or 0) > 0)
    pnl_total = sum((p.get("pnl_euros") or 0) for p in cette_sem)
    snap = lire_dernier_snapshot()
    etat = etat_portefeuille(prix_courants={})
    intuition = stats_intuition()

    # v5.3.7 — Narratif hebdo Gemini
    try:
        from agents.orchestrator_llm import narratif_hebdo
        narratif = narratif_hebdo(cette_sem, etat, intuition)
    except Exception as e:
        logger.warning(f"Narratif hebdo : {e}")
        narratif = ""
    bloc_narratif = f"\n## 📖 Synthèse de la semaine\n\n{narratif}\n" if narratif else ""

    rapport = f"""# AlphaSignal — Rapport Hebdomadaire — Semaine {annee}-W{semaine:02d}

Généré le : {now.strftime("%Y-%m-%d %H:%M UTC")}
{bloc_narratif}
## 📊 Performance de la semaine

- **Trades clôturés** : {nb} ({wins} gagnants, {nb - wins} perdants)
- **Win rate semaine** : {(wins / nb * 100) if nb else 0:.1f}%
- **P&L semaine** : {pnl_total:+.2f}€

## 💼 Portefeuille actuel

- Capital total : {etat['capital_total']:.2f}€
- Total value : {etat['total_value']:.2f}€  (P&L latent {etat['unrealized_pnl']:+.2f}€)
- Positions ouvertes : {etat['open_positions_count']}/{etat['max_positions']}
- Mode défensif : {'Oui' if etat['mode_defensif'] else 'Non'}

## 🧠 Intuition

- Décisions intuitives : {intuition['total']}
- Win rate intuition : {intuition['winrate_pct'] if intuition['winrate_pct'] is not None else 'N/A'}%
- En attente de résultat : {intuition['en_attente']}

## 💰 Budget Manager

```
{tableau_de_bord()}
```

## ⚠️ Disclaimer

Paper trading uniquement. Aucun ordre réel exécuté.
"""

    # Sauvegarde
    dossier = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports", "weekly",
    )
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"week_{annee}_W{semaine:02d}.md")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(rapport)
    logger.info(f"Rapport hebdo sauvegardé : {chemin}")
    return rapport


def main() -> int:
    import time as _t
    t0 = _t.time()
    logger.info("🟣 Cycle HEBDO — démarrage")
    skip, raison = doit_skipper(CYCLE)
    if skip:
        logger.info(f"Skip : {raison}")
        update_heartbeat(CYCLE, status="skipped", duration_sec=0)
        return 0
    if not acquerir_lock(CYCLE):
        update_heartbeat(CYCLE, status="skipped_lock", duration_sec=0)
        return 0
    try:
        rapport = _generer_rapport_hebdo()
        envoye = False
        try:
            from alerts.channels.email_channel import envoyer_email
            envoye = envoyer_email(
                sujet="[AlphaSignal] Rapport hebdomadaire",
                corps_texte=rapport,
            )
        except Exception as e:
            logger.error(f"Envoi email hebdo échoué : {e}")
        update_heartbeat(CYCLE, status="healthy", duration_sec=_t.time() - t0,
                         extra={"rapport_envoye": envoye})
        return 0
    except Exception as e:
        logger.error(f"❌ Cycle HEBDO échoué : {e}")
        logger.error(traceback.format_exc())
        update_heartbeat(CYCLE, status="error", duration_sec=_t.time() - t0,
                         extra={"error": str(e)[:200]})
        return 1
    finally:
        liberer_lock(CYCLE)


if __name__ == "__main__":
    sys.exit(main())
