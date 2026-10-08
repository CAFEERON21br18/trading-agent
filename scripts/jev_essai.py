"""
scripts/jev_essai.py — Un seul appel Jev réel, pour vérifier la clé, le modèle et le state.

Lancement (sur la tour) : .venv\\Scripts\\python.exe scripts\\jev_essai.py [TICKER]   (défaut : BTC-USD)

- State construit comme au cycle de 07h30 : mêmes analyses (analyser_actif_complet
  avec le sentiment global de l'étape 1 de l'orchestrateur), même liste blanche,
  même position_paper_ouverte. Pas de decider() : le state n'en a pas besoin, et le
  pipeline LLM écrirait en base.
- N'écrit RIEN en base (ni jev_observations, ni registre). Les analyses peuvent
  remplir le cache fichier data/cache/ et consomment du quota NewsAPI / Alpha Vantage.
- Indépendant de JEV_OBSERVE : c'est un essai manuel, pas une observation.

Codes de sortie : 0 OK ; 1 modèle renvoyé ≠ jev-1.13.0 ; 2 clé absente ; 3 échec de l'appel.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agents.jev.questions import MODELE, construire_questions, niveau_conviction
from agents.jev.state import construire_state, serialiser


def _sentiment_global() -> dict:
    """Identique à l'étape 1 de generer_rapport_quotidien (agents/orchestrator.py)."""
    from agents.analysts.sentiment_analyst.analyst import recuperer_fear_greed_crypto, calculer_correlation
    from agents.analysts.fundamental_analyst.onchain import recuperer_dominance_btc
    fg = recuperer_fear_greed_crypto()
    return {"fg_valeur": fg.get("valeur"), "fg_label": fg.get("label"),
            "dominance": recuperer_dominance_btc(),
            "corr_btc_spy": calculer_correlation("BTC-USD", "SPY")}


def main(ticker: str = "BTC-USD") -> int:
    if not config.TYPESAFE_API_KEY:
        print("TYPESAFE_API_KEY absente du .env : aucun appel. Ajoute la clé puis relance.")
        return 2
    from agents.asset_analyzer import analyser_actif_complet
    from utils.portfolio_db import lire_positions_ouvertes
    from agents.jev.observer import _creer_client

    analyses = analyser_actif_complet(ticker, _sentiment_global())
    ouverte = ticker in {p["ticker"] for p in lire_positions_ouvertes()}
    state = serialiser(construire_state(ticker, analyses, ouverte))
    print(f"== State envoyé ({ticker}) ==\n{state}\n")

    t0 = time.monotonic()
    try:
        resp = _creer_client().system_one(state=state, questions=construire_questions(),
                                          model=MODELE, timeout=config.JEV_TIMEOUT_SEC)
    except Exception as e:
        print(f"Échec de l'appel après {int((time.monotonic() - t0) * 1000)} ms : "
              f"{type(e).__name__}: {e}")
        return 3
    latence = int((time.monotonic() - t0) * 1000)

    action, conv, regime = resp.answers["action"], resp.answers["conviction"], resp.answers["regime"]
    print(f"Modèle renvoyé : {resp.model} (attendu {MODELE})")
    print(f"Latence : {latence} ms | jetons : {resp.usage.input_tokens} entrée, {resp.usage.output_tokens} sortie")
    print(f"\naction     : {action.choice} (confiance {action.confidence:.2f})")
    for option, p in action.probabilities.items():
        print(f"  {option:14s} {p:.3f}")
    print(f"conviction : score {conv.score:.2f}, niveau {niveau_conviction(conv.probabilities)} "
          f"(confiance {conv.confidence:.2f}) — probabilités {dict(conv.probabilities)}")
    print(f"regime     : {regime.choice} (confiance {regime.confidence:.2f}) — "
          f"moteur : {(analyses.get('context') or {}).get('regime_marche')}")
    print("\n⚠️ Essai paper : aucune décision, rien n'est enregistré.")
    if resp.model != MODELE:
        print(f"\n❌ Modèle renvoyé {resp.model} ≠ {MODELE} : ne pas activer JEV_OBSERVE (§7.6).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"))
