"""
agents/jev/state.py — State envoyé à Jev : les analyses que reçoit le moteur pour
ce ticker dans ce cycle, filtrées par LISTE BLANCHE, sérialisées en texte.

Exclu par construction (toute clé non listée est ignorée) :
- la décision du moteur (enregistrée dans jev_observations, jamais envoyée) ;
- les leçons et patterns en texte libre de memory/*.md (seuls winrate et
  nombre de trades de la mémoire paper sont gardés) ;
- toute donnée du portefeuille réel (aucune n'est dans `analyses` : ce module
  n'importe rien de utils/real_portfolio_db ni d'agents/real_advisor).

Ajout calculé en code : position_paper_ouverte (oui/non).
"""

import json

# Section → clés gardées (même noms que agents/asset_analyzer.py)
LISTE_BLANCHE = {
    "technique":   ("direction", "confiance", "prix", "tendance", "motifs"),
    "fondamental": ("direction", "confiance", "evaluation"),
    "sentiment":   ("direction", "confiance", "detail"),
    "risque":      ("valide", "rejets", "avertissements"),
    "context":     ("fg_valeur", "fg_label", "dominance", "corr_btc_spy",
                    "regime_marche", "regime_adx", "regime_global"),
}
# Sous-clés gardées du signal du Risk Manager (niveaux paper, pas de capital)
SIGNAL_RISQUE = ("direction", "prix_entree", "stop_loss", "target_1", "target_2",
                 "rr_1", "rr_2", "atr", "montant_investi")
PERF_MEMOIRE = ("trades", "winrate_pct")


def _garder(section: dict | None, cles: tuple) -> dict:
    section = section or {}
    return {k: section[k] for k in cles if k in section}


def construire_state(ticker: str, analyses: dict, position_ouverte: bool) -> dict:
    """Dict du state (pour les tests) ; utiliser serialiser() pour l'envoi."""
    state = {"ticker": ticker,
             "position_paper_ouverte": "oui" if position_ouverte else "non"}
    for section, cles in LISTE_BLANCHE.items():
        state[section] = _garder(analyses.get(section), cles)
    signal = (analyses.get("risque") or {}).get("signal")
    if isinstance(signal, dict):
        state["risque"]["signal"] = _garder(signal, SIGNAL_RISQUE)
    perf = (analyses.get("memory") or {}).get("perf")
    state["memoire_paper"] = _garder(perf, PERF_MEMOIRE) if isinstance(perf, dict) else {}
    return state


def serialiser(state: dict) -> str:
    """Texte stable (ordre des clés conservé) : c'est exactement ce qui est envoyé et stocké."""
    return json.dumps(state, ensure_ascii=False, indent=1, default=str)
