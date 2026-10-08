"""
agents/jev/questions.py — Questions posées à Jev, figées pour toute la durée du test.

⚠️ Ne rien modifier ici pendant le test (REGISTRE_CRITERES §7) : textes, ordre
des options et niveaux. Toute modification = nouvelle QUESTIONS_VERSION et
nouveau commit du registre ; les observations des deux versions ne se mélangent pas.

- action     : Choice, critère principal (p(acheter) ≥ 0,6). Ordre figé :
               ne_rien_faire, conserver, acheter (jev-1.13 favorise la 1re option,
               ce biais joue donc CONTRE l'hypothèse testée).
- conviction : Score à 4 niveaux, descriptif ; donne une taille hypothétique.
- regime     : Choice de contrôle de lecture, libellés de market_regime.py.
"""

QUESTIONS_VERSION = "v1"
# Modèle figé pour tout le test (pas l'alias jev-latest, qui peut changer sans prévenir)
MODELE = "jev-1.13.0"

ACTION_OPTIONS = ("ne_rien_faire", "conserver", "acheter")
REGIME_OPTIONS = ("haussier", "baissier", "range", "transition")

# Facteur de taille par niveau de conviction (0 rien, 1 petite, 2 moyenne, 3 pleine)
FACTEURS_CONVICTION = (0.0, 0.2, 0.5, 1.0)

SPECS = {
    "action": {
        "type": "choice",
        "instructions": ("À partir de ce state seul (analyses paper de l'actif, ce matin), "
                         "quelle action prendre sur cet actif pour les 5 prochains jours de bourse ?"),
        "criteria": {
            "ne_rien_faire": ("Aucune position paper n'est ouverte sur cet actif et les analyses "
                              "ne justifient pas d'en ouvrir une."),
            "conserver": ("Une position paper est déjà ouverte sur cet actif et les analyses "
                          "justifient de la garder telle quelle."),
            "acheter": ("Les analyses justifient d'ouvrir maintenant une position acheteuse "
                        "sur cet actif."),
        },
    },
    "conviction": {
        "type": "score",
        "instructions": "Dans ce state, comment les analyses de l'actif se situent-elles vis-à-vis d'un achat ?",
        "criteria": [
            "Aucune analyse du state n'est favorable à un achat.",
            "Une seule analyse est favorable à un achat ; les autres sont neutres ou défavorables.",
            "Plusieurs analyses sont favorables à un achat, mais au moins une est défavorable.",
            "Toutes les analyses non neutres sont favorables à un achat.",
        ],
    },
    "regime": {
        "type": "choice",
        "instructions": "Quel est le régime de marché de cet actif d'après ce state ?",
        "criteria": {
            "haussier": "Tendance haussière établie : force de tendance élevée, prix et moyennes longues orientés à la hausse.",
            "baissier": "Tendance baissière établie : force de tendance élevée, prix et moyennes longues orientés à la baisse.",
            "range": "Pas de tendance : force de tendance faible, prix sans direction nette.",
            "transition": "Situation intermédiaire : force de tendance moyenne, ou tendance forte sans alignement des moyennes.",
        },
    },
}

# Garde-fous : l'ordre figé est celui des constantes ci-dessus
assert tuple(SPECS["action"]["criteria"]) == ACTION_OPTIONS
assert tuple(SPECS["regime"]["criteria"]) == REGIME_OPTIONS
assert len(SPECS["conviction"]["criteria"]) == len(FACTEURS_CONVICTION)


def construire_questions() -> dict:
    """Objets du SDK (import tardif : rien n'est importé si l'observation est coupée)."""
    from typesafe_sdk import Choice, Score
    questions = {}
    for cle, spec in SPECS.items():
        classe = Choice if spec["type"] == "choice" else Score
        questions[cle] = classe(instructions=spec["instructions"], criteria=spec["criteria"])
    return questions


def niveau_conviction(probabilities: dict) -> int | None:
    """Niveau de probabilité maximale ; égalité → niveau le plus bas. Clés int ou str."""
    if not probabilities:
        return None
    probas = {int(k): float(v) for k, v in probabilities.items()}
    meilleure = max(probas.values())
    return min(k for k, v in probas.items() if v == meilleure)


def taille_hypothetique(niveau: int | None, montant_risque: float | None,
                        plafond_bm: float | None) -> float | None:
    """Ce que serait la taille à ce niveau, sous les règles actuelles. Jamais exécutée.
    Vide si pas de montant du Risk Manager, de niveau ou de plafond du Budget Manager."""
    if niveau is None or montant_risque is None or plafond_bm is None:
        return None
    return round(min(FACTEURS_CONVICTION[niveau] * float(montant_risque), float(plafond_bm)), 2)
