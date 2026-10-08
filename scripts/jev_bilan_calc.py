"""
scripts/jev_bilan_calc.py — Calculs du bilan Jev (REGISTRE_CRITERES §7), lecture seule.

Fonctions pures, testées sans réseau (tests/test_jev_bilan.py) :
- sélection : statut ok, version courante des questions, première ligne du jour
  par actif ;
- rendement J+5 (§0.2) : p0 = prix de la ligne, pJ+5 = clôture de la 5e barre
  journalière datée du jour d'observation ou après (la barre du jour clôt après
  7h30), coûts aller-retour 0,2 % (1,0 % crypto) ; orienté acheteur pour
  toutes les classes, afin de comparer « acheter ces actifs » entre classes ;
- unité indépendante (§0.1) : couple (groupe, semaine ISO), moyenne des
  observations du couple ;
- moyenne et IC à 95 % par bootstrap (10 000 tirages, graine fixe).
"""

import random
from datetime import date
from statistics import fmean

HORIZON = 5
SEUIL_ACHETER = 0.6
GROUPES = {  # REGISTRE_CRITERES §0.1
    "CRYPTO":     ("BTC-USD", "ETH-USD", "SOL-USD", "HBAR-USD", "CRO-USD"),
    "INDICES_US": ("SPY", "QQQ", "VOO", "NQ=F"),
    "SEMIS_IA":   ("NVDA", "AMD", "MU", "AMAT", "LITE", "VRT", "VST", "CEG"),
}


def groupe(ticker: str) -> str:
    """Groupe du §0.1 ; un actif hors groupe compte seul (son propre ticker)."""
    for nom, membres in GROUPES.items():
        if ticker in membres:
            return nom
    return ticker


def cout(ticker: str) -> float:
    return 0.010 if ticker in GROUPES["CRYPTO"] else 0.002


def premieres_du_jour(lignes: list[dict], version: str) -> list[dict]:
    """Lignes ok de la version, une par (actif, jour) : la première (horodatage)."""
    vues, gardees = set(), []
    for l in sorted(lignes, key=lambda x: (x["horodatage"], x.get("id") or 0)):
        if l["statut"] != "ok" or l["questions_version"] != version:
            continue
        cle = (l["ticker"], l["jour"])
        if cle not in vues:
            vues.add(cle)
            gardees.append(l)
    return gardees


def rendement(conn, ticker: str, jour: str, p0, h: int = HORIZON) -> float | None:
    """Rendement acheteur net de coûts à J+h ; None si p0 absent ou barre pas encore là."""
    if not p0:
        return None
    rows = conn.execute("SELECT close FROM prices WHERE ticker = ? AND timeframe = '1d' "
                        "AND substr(timestamp, 1, 10) >= ? AND close IS NOT NULL "
                        "ORDER BY timestamp LIMIT ?", (ticker, jour, h)).fetchall()
    if len(rows) < h:
        return None
    return float(rows[h - 1][0]) / float(p0) - 1 - cout(ticker)


def semaine_iso(jour: str) -> str:
    a, s, _ = date.fromisoformat(jour).isocalendar()
    return f"{a}-S{s:02d}"


def unites(obs: list[dict]) -> dict:
    """{(groupe, semaine ISO): moyenne des rendements} sur les observations ayant un rendement."""
    paquets = {}
    for o in obs:
        if o.get("rendement") is not None:
            paquets.setdefault((groupe(o["ticker"]), semaine_iso(o["jour"])), []).append(o["rendement"])
    return {k: fmean(v) for k, v in paquets.items()}


def bootstrap(valeurs: list[float], tirages: int = 10_000, graine: int = 0) -> tuple:
    """(moyenne, borne basse, borne haute) de l'IC à 95 % ; Nones si < 2 valeurs."""
    if len(valeurs) < 2:
        return (fmean(valeurs) if valeurs else None), None, None
    rng, n = random.Random(graine), len(valeurs)
    moyennes = sorted(fmean(rng.choices(valeurs, k=n)) for _ in range(tirages))
    return fmean(valeurs), moyennes[int(0.025 * tirages)], moyennes[int(0.975 * tirages) - 1]


def bootstrap_difference(a: list[float], b: list[float], tirages: int = 10_000,
                         graine: int = 1) -> tuple:
    """Moyenne(a) − moyenne(b), IC à 95 % (rééchantillonnage indépendant des deux classes)."""
    if len(a) < 2 or len(b) < 2:
        return None, None, None
    rng = random.Random(graine)
    diffs = sorted(fmean(rng.choices(a, k=len(a))) - fmean(rng.choices(b, k=len(b)))
                   for _ in range(tirages))
    return fmean(a) - fmean(b), diffs[int(0.025 * tirages)], diffs[int(0.975 * tirages) - 1]


def classes(obs: list[dict]) -> dict:
    """Observations SANS position paper ouverte, réparties pour le critère."""
    libres = [o for o in obs if not o.get("position_ouverte")]
    return {
        "jev_acheter":       [o for o in libres if (o.get("p_acheter") or 0) >= SEUIL_ACHETER],
        "jev_ne_rien_faire": [o for o in libres if (o.get("p_acheter") or 0) < SEUIL_ACHETER],
        "moteur_buy":        [o for o in libres if o.get("decision_moteur") == "BUY"],
        "toutes":            libres,
    }


def accord_regime(obs: list[dict]) -> tuple[int, int]:
    """(accords, comparables) entre regime_jev et context.regime_marche — contrôle de lecture."""
    comparables = [o for o in obs if o.get("regime_moteur") in ("haussier", "baissier", "range", "transition")]
    return sum(1 for o in comparables if o.get("regime_jev") == o["regime_moteur"]), len(comparables)
