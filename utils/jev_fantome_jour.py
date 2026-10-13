"""
utils/jev_fantome_jour.py — Bloc « Ce que Jev a dit ce matin » de la page Fantôme Jev
(REGISTRE_CRITERES §8.3, v1.5). LECTURE SEULE, descriptif, pas un critère.

Les actifs du dernier jour observé (cycle quotidien, questions de la version courante) :
choix de Jev, p(acheter), conviction, régime de Jev et régime du moteur, décision du
moteur, et ce qu'a fait le fantôme (achat, ou refus et motif du §8.2). Triés par
p(acheter) décroissant (sans p(acheter) en dernier), puis par ticker.
Aucun prix ni rendement ici : le §8.3 n'autorise que le P&L des positions du fantôme.
"""

from agents.jev.fantome import observations_retenues
from agents.jev.questions import QUESTIONS_VERSION
from scripts.jev_bilan_calc import SEUIL_ACHETER
from utils import jev_db
from utils.jev_paper_comparaison import table_existe


def _journal_du_fantome(conn, ids: list) -> dict:
    """{observation_id: (evenement, motif)} : entrée ou refus inscrits par le fantôme."""
    if not ids or not table_existe(conn, "jev_paper_journal"):
        return {}
    rows = conn.execute("SELECT observation_id, evenement, motif FROM jev_paper_journal "
                        f"WHERE evenement != 'sortie' AND observation_id IN ({','.join('?' * len(ids))})",
                        ids).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def _action_du_fantome(o: dict, journal: dict, retenue: bool) -> dict:
    """achat | refus (motif du §8.2) | pas_candidat (p < 0,6) | en_attente (fantôme pas
    encore passé) | hors_observation (ligne non retenue au §7.1 : erreur, écartée…)."""
    if not retenue:
        motif = o["statut"] if o["statut"] != "ok" else f"modèle {o.get('modele')}"
        return {"action": "hors_observation", "motif": motif}
    if o["id"] in journal:
        evenement, motif = journal[o["id"]]
        return {"action": "achat" if evenement == "entree" else "refus", "motif": motif}
    if (o.get("p_acheter") or 0) < SEUIL_ACHETER:
        return {"action": "pas_candidat", "motif": None}
    return {"action": "en_attente", "motif": None}


def _ligne(o: dict, journal: dict, retenue: bool) -> dict:
    return {"ticker": o["ticker"], "statut": o["statut"], "choix": o.get("action_jev"),
            "p_acheter": o.get("p_acheter"), "conviction_niveau": o.get("conviction_niveau"),
            "regime_jev": o.get("regime_jev"), "regime_moteur": o.get("regime_moteur"),
            "decision_moteur": o.get("decision_moteur"), "fantome": _action_du_fantome(o, journal, retenue)}


def cle_de_tri(actif: dict) -> tuple:
    """p(acheter) décroissant, sans p(acheter) en dernier, puis ticker."""
    p = actif["p_acheter"]
    return (p is None, -(p or 0.0), actif["ticker"])


def derniere_observation(conn) -> dict:
    """{jour, actifs} du dernier jour observé ; une ligne par actif : l'observation
    retenue au §7.1 (celle que lit le fantôme), sinon la première ligne du jour."""
    lignes = [l for l in jev_db.lire(conn) if l["questions_version"] == QUESTIONS_VERSION]
    if not lignes:
        return {"jour": None, "actifs": []}
    jour = max(l["jour"] for l in lignes)
    retenues = {o["ticker"]: o for o in observations_retenues(conn) if o["jour"] == jour}
    autres = {}
    for l in lignes:  # lire() trie par horodatage : on garde la première du jour
        if l["jour"] == jour and l["ticker"] not in retenues:
            autres.setdefault(l["ticker"], l)
    journal = _journal_du_fantome(conn, [o["id"] for o in retenues.values()])
    actifs = ([_ligne(o, journal, True) for o in retenues.values()]
              + [_ligne(l, journal, False) for l in autres.values()])
    return {"jour": jour, "actifs": sorted(actifs, key=cle_de_tri)}
