"""
agents/jev/fantome.py — Portefeuille fantôme Jev (REGISTRE_CRITERES §8), DESCRIPTIF.

Appelé par agents/orchestrator.py juste après l'observation Jev du cycle
quotidien. Rejoue dans l'ordre des jours les observations du §7.1 pas encore
traitées ; pour chaque jour :
1. sorties : positions dont la 5e barre (J+5 du §7.1) est datée d'avant le jour ;
2. entrées : p(acheter) ≥ 0,6, pas de position paper (figée dans l'observation),
   pas de position fantôme ; par p(acheter) décroissant, puis ticker.
Un jour = une transaction : relancer ne crée jamais de doublon.

Garanties : aucune table du paper lue ni écrite, aucun appel à Jev ni à une
source de prix, aucune exception vers le cycle. Le log ne contient que des
compteurs : le P&L n'est affiché que par la ligne du dashboard (§8.3).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import config
from utils.logger import get_logger
from utils import jev_db, jev_paper_db
from agents.jev.questions import MODELE, QUESTIONS_VERSION
from agents.jev import fantome_regles as regles
from scripts.jev_bilan_calc import premieres_du_jour

logger = get_logger(__name__)

CYCLE = "quotidien"  # comme l'observation : ni tactical, ni lancement manuel


def observations_retenues(conn) -> list[dict]:
    """Observations du §7.1 : même sélection que scripts/jev_bilan.py (main)."""
    lignes = [l for l in jev_db.lire(conn) if l["questions_version"] == QUESTIONS_VERSION]
    return premieres_du_jour([l for l in lignes if l["statut"] != "ok" or l.get("modele") == MODELE],
                             QUESTIONS_VERSION)


def _barres(conn, ticker: str, jour: str) -> list:
    """Les HORIZON premières barres journalières datées du jour ou après (requête du §7.1)."""
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT substr(timestamp, 1, 10), close FROM prices WHERE ticker = ? AND timeframe = '1d' "
        "AND substr(timestamp, 1, 10) >= ? AND close IS NOT NULL ORDER BY timestamp LIMIT ?",
        (ticker, jour, regles.HORIZON)).fetchall()]


def _sorties(conn, jour: str) -> int:
    n = 0
    for p in jev_paper_db.positions_ouvertes(conn):
        barre = regles.barre_sortie(_barres(conn, p["ticker"], p["jour_entree"]), jour)
        if barre:
            jev_paper_db.fermer(conn, p, jour, barre[0], barre[1], regles.resultat(p, barre[1]))
            n += 1
    return n


def _entrees(conn, jour: str, candidats: list[dict]) -> tuple[int, int]:
    ouvertes = jev_paper_db.positions_ouvertes(conn)
    tickers = {p["ticker"] for p in ouvertes}
    investi = sum(p["montant_investi"] for p in ouvertes)
    achats = refus = 0
    for o in sorted(candidats, key=lambda x: (-x["p_acheter"], x["ticker"])):
        motif, details = regles.motif_avant_taille(o, tickers), {}
        if motif is None:
            entree, motif, details = regles.taille(o, investi, len(tickers),
                                                   config.MAX_POSITIONS_SIMULTANEES, config.CAPITAL)
        if motif:
            jev_paper_db.refuser(conn, o, jour, motif, details)
            refus += 1
            continue
        jev_paper_db.ouvrir(conn, o, jour, entree, details)
        tickers.add(o["ticker"])
        investi += entree["montant"]
        achats += 1
    return achats, refus


def traiter(conn, aujourd_hui: str) -> dict:
    """Rejoue les jours en attente, puis le jour courant. Lève en cas d'erreur (jour annulé)."""
    deja = jev_paper_db.observations_traitees(conn)
    candidats = [o for o in observations_retenues(conn)
                 if (o.get("p_acheter") or 0) >= regles.SEUIL_ACHETER
                 and o["id"] not in deja and o["jour"] <= aujourd_hui]
    resume = {"jours": 0, "entrees": 0, "refus": 0, "sorties": 0}
    for jour in sorted({o["jour"] for o in candidats} | {aujourd_hui}):
        try:
            resume["sorties"] += _sorties(conn, jour)  # les sorties d'un jour avant ses entrées
            achats, refus = _entrees(conn, jour, [o for o in candidats if o["jour"] == jour])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        resume["jours"] += 1
        resume["entrees"] += achats
        resume["refus"] += refus
    return resume


def executer(cycle: str, aujourd_hui: str | None = None) -> dict | None:
    """Point d'entrée du cycle. None hors cycle quotidien ou en cas d'erreur ; ne lève jamais."""
    if cycle != CYCLE:
        return None
    try:
        jour = aujourd_hui or datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()
        conn = jev_paper_db.connexion()
        try:
            resume = traiter(conn, jour)
        finally:
            conn.close()
        logger.info(f"Fantôme Jev : {resume['entrees']} entrée(s), {resume['sorties']} sortie(s), "
                    f"{resume['refus']} refus, {resume['jours']} jour(s) traité(s)")
        return resume
    except Exception as e:
        logger.error(f"Fantôme Jev : passage interrompu, cycle non affecté ({e})")
        return None
