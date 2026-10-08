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
- moyenne et IC à 95 % par bootstrap par grappes de semaines ISO
  (10 000 tirages, graines fixes) ;
- contrôle de lecture du régime sur les 10 premiers jours de bourse.
"""

import random
from datetime import date
from statistics import fmean

HORIZON = 5
SEUIL_ACHETER = 0.6
TIRAGES = 10_000                    # bootstrap par grappes de semaines ISO (§7.4)
GRAINE_MOYENNE, GRAINE_ECART, GRAINE_ECART_MOTEUR = 7001, 7002, 7003
JOURS_CONTROLE, ACCORD_MIN = 10, 0.50   # contrôle de lecture du régime (§7.2)
COUTS = {"CRYPTO": 0.010}           # aller-retour (§0.2, §7.1) ; 0,2 % pour tout le reste
COUT_DEFAUT = 0.002
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
    return COUTS.get(groupe(ticker), COUT_DEFAUT)


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


def _par_semaine(unites_: dict) -> dict:
    """{semaine ISO: [valeurs des unités de cette semaine]} — une grappe par semaine."""
    grappes = {}
    for (_, semaine), v in unites_.items():
        grappes.setdefault(semaine, []).append(v)
    return grappes


def bootstrap_grappes(unites_: dict, tirages: int = TIRAGES, graine: int = GRAINE_MOYENNE) -> tuple:
    """(moyenne des unités, borne basse, borne haute) de l'IC à 95 %, en tirant des
    SEMAINES ISO avec remise (les unités d'une même semaine ne sont pas indépendantes).
    Bornes None si moins de 2 semaines."""
    if not unites_:
        return None, None, None
    grappes = _par_semaine(unites_)
    semaines = sorted(grappes)
    moyenne = fmean(unites_.values())
    if len(semaines) < 2:
        return moyenne, None, None
    rng = random.Random(graine)
    stats = sorted(fmean([v for s in rng.choices(semaines, k=len(semaines)) for v in grappes[s]])
                   for _ in range(tirages))
    return moyenne, stats[int(0.025 * tirages)], stats[int(0.975 * tirages) - 1]


def bootstrap_grappes_difference(ua: dict, ub: dict, tirages: int = TIRAGES,
                                 graine: int = GRAINE_ECART) -> tuple:
    """Moyenne(ua) − moyenne(ub), IC à 95 % : les MÊMES semaines tirées pour les deux
    classes (appariement par semaine). Tirage sans unité dans une classe : ignoré."""
    if not ua or not ub:
        return None, None, None
    ga, gb = _par_semaine(ua), _par_semaine(ub)
    semaines = sorted(set(ga) | set(gb))
    ecart = fmean(ua.values()) - fmean(ub.values())
    if len(semaines) < 2:
        return ecart, None, None
    rng, stats = random.Random(graine), []
    for _ in range(tirages):
        tirees = rng.choices(semaines, k=len(semaines))
        a = [v for s in tirees for v in ga.get(s, [])]
        b = [v for s in tirees for v in gb.get(s, [])]
        if a and b:
            stats.append(fmean(a) - fmean(b))
    if len(stats) < 2:
        return ecart, None, None
    stats.sort()
    return ecart, stats[int(0.025 * len(stats))], stats[int(0.975 * len(stats)) - 1]


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


def controle_regime(obs: list[dict]) -> dict:
    """Accord régime Jev / moteur sur les 10 premiers jours de bourse (lun-ven) observés.
    statut : en_cours (< 10 jours), ok, ou arret (accord < 50 % : test arrêté, §7.2)."""
    jours = sorted({o["jour"] for o in obs if date.fromisoformat(o["jour"]).weekday() < 5})
    if len(jours) < JOURS_CONTROLE:
        return {"statut": "en_cours", "jours": len(jours), "accords": None, "comparables": None}
    limite = jours[JOURS_CONTROLE - 1]
    accords, comparables = accord_regime([o for o in obs if o["jour"] <= limite])
    taux = accords / comparables if comparables else 0.0
    return {"statut": "ok" if taux >= ACCORD_MIN else "arret", "jours": JOURS_CONTROLE,
            "accords": accords, "comparables": comparables, "jusqu_au": limite}

