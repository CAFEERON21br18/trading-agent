"""
agents/decision_regles.py — Paramètres et règles de base du Decision Engine : pondérations, seuils,
score par sous-agent, convergences et contradictions, overrides (vetos).
Sorti de agents/decision_engine.py (règle des 200 lignes) ; decision_engine.py réexporte tout :
les imports existants (dont utils/registre.py pour POIDS et les seuils) ne changent pas.
"""

import config


# ── Pondérations (somme = 100%) ──────────────────────────────────────────────
POIDS = {"technique": 0.35, "fondamental": 0.25, "sentiment": 0.20, "risque": 0.20}

# ── Seuils de décision (v4.1 — moins prudent pour favoriser l'apprentissage) ──
SEUIL_BUY              = config.SEUIL_BUY    # BUY normal si score ≥ SEUIL_BUY (défaut +2.0 ; avant v4.1 : +3.0)
SEUIL_SELL             = config.SEUIL_SELL   # SELL normal si score ≤ SEUIL_SELL (défaut -2.0 ; avant v4.1 : -3.0)
SEUIL_LEARNING         = 0.5   # BUY/SELL learning (micro-position) si |score| ≥ 0.5
SEUIL_CONTRADICTION    = 8     # contradiction majeure : confiance ≥ 8/10 (avant : 7)
WINRATE_PRUDENCE       = 35.0  # win rate sous lequel on exige confiance plus élevée
TAILLE_LEARNING_PCT    = 0.2   # micro-position = 20% du budget alloué
TAILLE_CONTRADICTION   = 0.5   # si contradiction → taille réduite à 50%


def _direction_a_signe(direction: str) -> int:
    """BULLISH/ACHAT → +1, BEARISH/VENTE → -1, NEUTRE/HOLD → 0."""
    d = (direction or "").upper()
    if d in ("BULLISH", "ACHAT", "BUY", "LONG", "POSITIF"):
        return 1
    if d in ("BEARISH", "VENTE", "SELL", "SHORT", "NÉGATIF", "NEGATIF"):
        return -1
    return 0


def _normaliser(analyses: dict) -> dict:
    """Pour chaque sous-agent : signe × confiance × poids = score."""
    scores = {}
    for nom, poids in POIDS.items():
        a = analyses.get(nom, {})
        signe     = _direction_a_signe(a.get("direction", "NEUTRE"))
        confiance = float(a.get("confiance", 0) or 0)
        scores[nom] = signe * confiance * poids
    return scores


def _convergences_contradictions(analyses: dict) -> tuple[list[str], list[str]]:
    """Identifie les paires d'agents qui convergent ou se contredisent."""
    convergences   = []
    contradictions = []
    noms = ["technique", "fondamental", "sentiment"]
    for i, n1 in enumerate(noms):
        for n2 in noms[i + 1:]:
            a1, a2 = analyses.get(n1, {}), analyses.get(n2, {})
            s1, s2 = _direction_a_signe(a1.get("direction")), _direction_a_signe(a2.get("direction"))
            c1, c2 = float(a1.get("confiance", 0) or 0), float(a2.get("confiance", 0) or 0)
            if s1 != 0 and s1 == s2 and c1 >= 5 and c2 >= 5:
                sens = "haussière" if s1 > 0 else "baissière"
                convergences.append(f"{n1.capitalize()} + {n2} convergent ({sens}, confiance {c1:.0f}/{c2:.0f})")
            elif s1 != 0 and s2 != 0 and s1 != s2 and c1 >= SEUIL_CONTRADICTION and c2 >= SEUIL_CONTRADICTION:
                contradictions.append(f"{n1.capitalize()} ({a1.get('direction')}) ⚠️ {n2} ({a2.get('direction')}) — confiance {c1:.0f}/{c2:.0f}")
    return convergences, contradictions


def _verifier_overrides(ticker: str, analyses: dict) -> list[str]:
    """Liste les facteurs qui BLOQUENT le trade (veto)."""
    overrides = []

    # Risk Manager veto
    risque = analyses.get("risque", {})
    if risque and not risque.get("valide", True):
        rejets = risque.get("rejets", [])
        overrides.append(f"Risk Manager rejette : {' | '.join(rejets)}")

    # Mauvais track record sur cet actif
    perf = analyses.get("memory", {}).get("perf")
    if perf and perf["trades"] >= 5 and perf["winrate_pct"] < WINRATE_PRUDENCE:
        overrides.append(
            f"Track record défavorable sur {ticker} : {perf['winrate_pct']:.0f}% "
            f"de winrate sur {perf['trades']} trades"
        )

    # Fear & Greed extrême combiné à un signal contraire (contrarian)
    ctx = analyses.get("context", {})
    fg = ctx.get("fg_valeur")
    tech_dir = _direction_a_signe(analyses.get("technique", {}).get("direction"))
    if fg is not None:
        if fg <= 20 and tech_dir < 0:
            overrides.append(f"Extreme Fear (F&G {fg}) contredit signal VENTE — possible bottom")
        elif fg >= 80 and tech_dir > 0:
            overrides.append(f"Extreme Greed (F&G {fg}) contredit signal ACHAT — possible top")

    return overrides
