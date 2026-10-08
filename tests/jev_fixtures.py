"""
tests/jev_fixtures.py — Données partagées des tests Jev : analyses avec secrets
(leçons, patterns, données « réelles ») qui ne doivent jamais partir, et client
Jev simulé (aucun réseau, aucune clé).
"""

from types import SimpleNamespace

SECRET_LECON, SECRET_PATTERN, SECRET_REEL = "LECON-SECRETE", "PATTERN-SECRET", "REEL-SECRET"


def analyses_exemple(ticker="BTC-USD") -> dict:
    return {
        "technique": {"direction": "ACHAT", "confiance": 3, "prix": 100.0, "tendance": "Haussière",
                      "motifs": ["MACD > Signal (haussier) (+1)"], "detail": "x"},
        "fondamental": {"direction": "NEUTRE", "confiance": 0, "evaluation": "N/A", "detail": "N/A"},
        "sentiment": {"direction": "NEUTRE", "confiance": 2, "narratif": "1+ / 1- / 0~", "detail": "1+ / 1- / 0~"},
        "risque": {"valide": True, "rejets": [], "avertissements": [], "direction": "ACHAT", "confiance": 0,
                   "signal": {"stop_loss": 95.0, "montant_investi": 80.0, "capital_investissable": SECRET_REEL}},
        "memory": {"perf": {"trades": 4, "winrate_pct": 50.0, "pnl_moyen_pct": 1.0},
                   "lecons": [SECRET_LECON], "patterns": [SECRET_PATTERN]},
        "context": {"fg_valeur": 55, "regime_marche": "haussier", "inconnu": SECRET_REEL},
        "reel": {"positions": SECRET_REEL},  # clé inattendue : doit être ignorée
    }


def decisions_exemple() -> list[dict]:
    return [{"ticker": t, "analyses": analyses_exemple(t),
             "decision": {"ticker": t, "decision": "BUY", "style": "learning", "score_composite": 1.05,
                          "confidence": 5, "taille_factor": 0.2}} for t in ("BTC-USD", "SPY", "NVDA")]


class ClientSimule:
    """Imite TypeSafeClient.system_one ; erreur optionnelle ; garde les states reçus."""
    def __init__(self, erreur=None, p_acheter=0.7):
        self.erreur, self.p, self.states = erreur, p_acheter, []

    def system_one(self, state, questions, model=None, timeout=None):
        self.states.append(state)
        if self.erreur:
            raise self.erreur
        reste = (1 - self.p) / 2
        answers = {
            "action": SimpleNamespace(choice="acheter", confidence=0.6, probabilities={
                "ne_rien_faire": reste, "conserver": reste, "acheter": self.p}),
            "conviction": SimpleNamespace(score=1.8, probabilities={0: 0.1, 1: 0.2, 2: 0.4, 3: 0.3}),
            "regime": SimpleNamespace(choice="haussier"),
        }
        return SimpleNamespace(model=model or "jev-test", answers=answers,
                               usage=SimpleNamespace(input_tokens=120, output_tokens=6),
                               model_dump=lambda mode=None: {"model": "jev-test"})
