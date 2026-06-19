"""
agents/knowledge/knowledge_base.py — Base de connaissances théoriques v5.0
Organisée par DOMAINES. Chaque entrée = courte + actionnable.
Le Decision Engine et l'analyse pré-trade vont chercher ici les concepts pertinents.
"""

# ── DOMAINE 1 : Analyse technique avancée ───────────────────────────────────
TECHNIQUE = {
    "dow_theory": (
        "Tendances primaire (>1 an), secondaire (3 sem-3 mois), mineure (<3 sem). "
        "Une tendance reste en vigueur jusqu'à preuve claire du contraire."
    ),
    "patterns_chartistes_fiables": (
        "Top 5 par taux de réussite historique : "
        "1. Inverse head-and-shoulders au support (~70%), "
        "2. Triangle ascendant breakout volume (~67%), "
        "3. Cup-and-handle (~65%), "
        "4. Double bottom avec divergence RSI (~63%), "
        "5. Bull flag après impulsion (~60%)."
    ),
    "bougies_japonaises_cles": (
        "Hammer/Inverted Hammer au support → renversement bullish potentiel. "
        "Shooting Star/Hanging Man à la résistance → bearish. "
        "Engulfing : bougie qui avale entièrement la précédente = signal fort. "
        "Doji au sommet/creux = indécision, attente de confirmation."
    ),
    "volume_spread_analysis": (
        "Climax volume (volume énorme + range large) = épuisement de la tendance. "
        "No-demand bar (faible range + faible volume en hausse) = absence d'acheteurs. "
        "Effort vs Result : si volume haut mais prix ne bouge presque pas = absorption."
    ),
    "confluence_rule": (
        "Un signal isolé vaut peu. Setup A+ = au moins 3 éléments alignés "
        "(ex : support historique + Fib 61.8% + RSI oversold + bougie marteau). "
        "Plus de confluence → plus de conviction → taille plus grande."
    ),
    "divergence_rsi": (
        "Divergence haussière : prix fait un plus bas, RSI fait un plus haut bas "
        "→ momentum baissier s'épuise, retournement haussier probable. "
        "Inverse pour divergence baissière. À confirmer par cassure du dernier swing."
    ),
}

# ── DOMAINE 2 : Analyse fondamentale ────────────────────────────────────────
FONDAMENTAL = {
    "pe_ratio": (
        "P/E < 15 = potentiellement value (à comparer au secteur). "
        "P/E > 30 = pricing de croissance forte (vérifier qu'elle existe). "
        "P/E > 50 sans croissance = spéculation pure."
    ),
    "moat_buffett": (
        "Avantage concurrentiel durable : marque (Coca, Apple), réseau "
        "(Visa, Meta), coûts (Costco, Amazon), switching cost (Microsoft), "
        "régulation (utilities). Un moat solide justifie un P/E plus élevé."
    ),
    "ratios_sante_financiere": (
        "Current Ratio > 1.5 = liquidité OK. Debt/Equity < 1 = endettement maîtrisé. "
        "FCF Yield > 5% = entreprise génère du cash. ROE > 15% sur 5 ans = qualité."
    ),
    "earnings_jeux": (
        "Buy the rumor / sell the news : pricing souvent fait avant. "
        "Surprise positive + guidance relevée = gap haussier durable. "
        "Beat earnings mais guidance baissée = piège, vendre."
    ),
    "crypto_tokenomics": (
        "Vérifier : émission max, schedule de vesting (unlocks), répartition "
        "(équipe/VC vs public), utilité réelle du token (gouvernance, gas, staking). "
        "Loi de Metcalfe : valeur du réseau ∝ (nb users)²."
    ),
}

# ── DOMAINE 3 : Macro-économie ──────────────────────────────────────────────
MACRO = {
    "cycle_economique": (
        "Expansion (taux bas, croissance, FOMO) → Pic (inflation, hausse taux) → "
        "Récession (chômage, baisse) → Reprise. "
        "Actions surperforment en expansion ; obligations en récession ; or en stagflation."
    ),
    "courbe_taux_inversion": (
        "10Y < 2Y = inversion = signal historique de récession à 12-18 mois. "
        "Pas de garantie, mais à prendre au sérieux."
    ),
    "rotation_sectorielle": (
        "Early cycle : techno, conso discrétionnaire. "
        "Mid : industrie, matériaux. Late : énergie, santé. "
        "Récession : staples, utilities, or."
    ),
    "fed_pivot": (
        "Anticipation de baisse de taux = pump des actifs risqués (crypto, growth). "
        "Réalisation de la baisse = souvent vente sur la nouvelle."
    ),
    "risk_on_risk_off": (
        "Risk-on : actions montent, BTC monte, DXY baisse, or stable. "
        "Risk-off : refuge or, JPY, USD, obligations US ; risk assets chutent."
    ),
}

# ── DOMAINE 4 : Gestion du risque ───────────────────────────────────────────
RISK = {
    "kelly_criterion": (
        "Taille optimale = (winrate × (R:R+1) - 1) / R:R "
        "Avec 60% winrate et R:R 1:2 → Kelly = 40%. "
        "En pratique, utiliser fractional Kelly (1/4 ou 1/2) car volatilité."
    ),
    "asymetrie": (
        "Règle d'or : couper les pertes vite (-2 à -5%), laisser courir les gains. "
        "1 trade qui fait +30% peut compenser 6 stop-loss à -5%."
    ),
    "drawdown_max": (
        "Pour récupérer un drawdown de X%, il faut un gain de X/(1-X). "
        "-10% → +11% ; -25% → +33% ; -50% → +100%. "
        "Protéger le capital est plus important que maximiser le gain."
    ),
    "diversification": (
        "Corrélation parfaite entre actifs = pas de diversification. "
        "Idéal : 5-15 actifs faiblement corrélés (ex : actions tech + or + crypto + obligations)."
    ),
    "rr_minimum": (
        "Espérance mathématique = (winrate × gain) - ((1-winrate) × perte). "
        "Pour être profitable avec 50% winrate, R:R minimum 1:1.5. "
        "Pour 40% winrate, R:R minimum 1:2.5."
    ),
}

# ── DOMAINE 5 : Psychologie de marché ───────────────────────────────────────
PSYCHO = {
    "cycle_emotions": (
        "Euphorie (sommet) → déni (chute) → peur → panique (vente massive, capitulation) "
        "→ espoir (rebond) → optimisme (nouvelle tendance) → euphorie. "
        "Trader à contre-courant les extrêmes émotionnels."
    ),
    "fear_greed_contrarian": (
        "F&G < 20 (Extreme Fear) = souvent un bon moment d'accumulation. "
        "F&G > 80 (Extreme Greed) = prudence, profits partiels. "
        "Buffett : Be fearful when others are greedy."
    ),
    "fomo_fud": (
        "FOMO (Fear Of Missing Out) : acheter le sommet par peur de rater. "
        "FUD (Fear, Uncertainty, Doubt) : vendre le creux par peur du pire. "
        "Reconnaître ces émotions chez soi-même = avantage."
    ),
    "narrative_driven": (
        "Le récit (story) peut dominer les fondamentaux à court terme "
        "(ex: GameStop 2021, AI hype 2023). À moyen terme, les fondamentaux reprennent."
    ),
}


def chercher_concepts(question: str, max_concepts: int = 3) -> list[dict]:
    """
    Cherche les concepts pertinents par mots-clés simples.
    Retourne liste de {domaine, concept, definition}.
    """
    domaines = {
        "technique":   TECHNIQUE,
        "fondamental": FONDAMENTAL,
        "macro":       MACRO,
        "risk":        RISK,
        "psycho":      PSYCHO,
    }
    q = question.lower()
    matches = []
    for domaine, dico in domaines.items():
        for cle, definition in dico.items():
            cle_clean = cle.replace("_", " ")
            if cle_clean in q or any(w in q for w in cle_clean.split() if len(w) > 3):
                matches.append({"domaine": domaine, "concept": cle, "definition": definition})
    return matches[:max_concepts]


def concepts_pour_decision(direction: str, score: float, confiance: int) -> list[str]:
    """Retourne les principes applicables au contexte de la décision."""
    principes = []
    if confiance < 6:
        principes.append("CONFLUENCE : " + TECHNIQUE["confluence_rule"])
    if abs(score) < 3:
        principes.append("R:R MIN : " + RISK["rr_minimum"])
    principes.append("ASYMÉTRIE : " + RISK["asymetrie"])
    return principes
