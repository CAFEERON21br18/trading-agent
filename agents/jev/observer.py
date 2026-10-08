"""
agents/jev/observer.py — Observation Jev dans le cycle quotidien (observation SEULE).

Deux temps, appelés par agents/orchestrator.py :
1. preparer_observations(decisions, cycle) — juste après les décisions, AVANT
   l'exécution paper (qui modifie analyses["risque"]) : fige le state texte,
   la décision du moteur, la position paper et le plafond du Budget Manager.
2. observer(lot) — après l'exécution et le registre : un appel par actif,
   ordre tiré au sort chaque jour (graine = date), timeout 3 s sans nouvelle
   tentative, budget global 120 s ; écrit dans jev_observations.

Garanties : rien ne se passe sans JEV_OBSERVE=1 ; aucune sortie n'est
renvoyée au moteur ; aucune exception ne remonte au cycle.
"""

import random
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
from utils.logger import get_logger
from agents.jev.questions import (MODELE, QUESTIONS_VERSION, construire_questions,
                                  niveau_conviction, taille_hypothetique)
from agents.jev.state import construire_state, serialiser

logger = get_logger(__name__)

CYCLE_OBSERVE = "quotidien"  # ni tactical, ni lancement manuel, ni conseiller réel


def _contexte_paper() -> tuple[set, str | None, float | None]:
    """(tickers en position paper, mode du BM, max par trade en €) — lecture seule."""
    from utils.portfolio_db import lire_positions_ouvertes
    from agents.budget_manager.strategy import detecter_mode, parametres_mode
    from agents.budget_manager.manager import _cash_disponible_actuel
    ouvertes = {p["ticker"] for p in lire_positions_ouvertes()}
    try:
        mode = detecter_mode()
        plafond = parametres_mode(mode)["max_conviction_par_trade"] / 100 * _cash_disponible_actuel(mode)
        return ouvertes, mode, round(plafond, 2)
    except Exception as e:
        logger.warning(f"Jev : plafond du Budget Manager indisponible ({e}) — tailles vides")
        return ouvertes, None, None


def preparer_observations(decisions: list[dict], cycle: str) -> list[dict]:
    """Fige ce qui sera envoyé et comparé. [] si coupé, hors cycle quotidien ou en erreur."""
    if not config.JEV_OBSERVE or cycle != CYCLE_OBSERVE:
        return []
    try:
        ouvertes, mode, plafond = _contexte_paper()
        lot = []
        for d in decisions:
            ticker, an, dec = d["ticker"], d["analyses"], d["decision"]
            signal = (an.get("risque") or {}).get("signal") or {}
            lot.append({
                "ticker": ticker, "cycle": cycle,
                "state": serialiser(construire_state(ticker, an, ticker in ouvertes)),
                "position_ouverte": int(ticker in ouvertes),
                "prix": (an.get("technique") or {}).get("prix"),
                "decision_moteur": dec.get("decision"), "style_moteur": dec.get("style"),
                "score_moteur": dec.get("score_composite"), "confiance_moteur": dec.get("confidence"),
                "montant_risque": signal.get("montant_investi"),
                "plafond_bm": plafond, "mode_bm": mode,
                "regime_moteur": (an.get("context") or {}).get("regime_marche"),
            })
        return lot
    except Exception as e:
        logger.error(f"Jev : préparation impossible, aucune observation ce cycle ({e})")
        return []


def _creer_client():
    """Client du SDK : clé du .env, modèle figé, 3 s, aucune nouvelle tentative. None si pas de clé."""
    if not config.TYPESAFE_API_KEY:
        logger.error("Jev : JEV_OBSERVE=1 mais TYPESAFE_API_KEY vide — aucun appel")
        return None
    from typesafe_sdk import RetryPolicy, TypeSafeClient
    return TypeSafeClient(api_key=config.TYPESAFE_API_KEY, model=MODELE, timeout=config.JEV_TIMEOUT_SEC,
                          retry=RetryPolicy(max_retries=0))


def _lire_reponse(resp, item: dict) -> dict:
    """Extrait les champs de comparaison ; réponses complètes gardées en JSON."""
    action, conv, regime = (resp.answers["action"], resp.answers["conviction"],
                            resp.answers["regime"])
    p = action.probabilities or {}
    niveau = niveau_conviction(conv.probabilities)
    usage = resp.usage
    return {
        "statut": "ok", "modele": resp.model,
        "action_jev": action.choice, "confiance": action.confidence,
        "p_acheter": p.get("acheter"), "p_conserver": p.get("conserver"),
        "p_ne_rien_faire": p.get("ne_rien_faire"),
        "conviction_niveau": niveau, "conviction_score": conv.score,
        "taille_hypothetique": taille_hypothetique(niveau, item["montant_risque"], item["plafond_bm"]),
        "regime_jev": regime.choice,
        "reponses": resp.model_dump(mode="json"),
        "jetons_entree": getattr(usage, "input_tokens", None),
        "jetons_sortie": getattr(usage, "output_tokens", None),
    }


def _enregistrer(ligne: dict) -> None:
    try:
        from utils.jev_db import inserer
        inserer(ligne)
    except Exception as e:
        logger.error(f"Jev : écriture jev_observations {ligne.get('ticker')} impossible ({e})")


def observer(lot: list[dict], client=None, horloge=time.monotonic) -> dict:
    """Interroge Jev pour chaque actif du lot. Ne lève jamais ; le résultat n'est lu par aucun vote."""
    resume = {"appels": 0, "ok": 0, "erreurs": 0, "ecartes": []}
    if not config.JEV_OBSERVE or not lot:
        return resume
    try:
        client = client or _creer_client()
        if client is None:
            return resume
        questions = construire_questions()
        jour = datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()  # jour de Lisbonne
        ordre = sorted(lot, key=lambda x: x["ticker"])
        random.Random(jour).shuffle(ordre)  # graine = date : reproductible, pas toujours les mêmes écartés
        debut = horloge()
        for item in ordre:
            ligne = dict(item)
            ligne.update(jour=jour, questions_version=QUESTIONS_VERSION,
                         horodatage=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            if horloge() - debut >= config.JEV_BUDGET_SEC:
                resume["ecartes"].append(item["ticker"])
                _enregistrer({**ligne, "statut": "ecarte", "erreur": "budget du cycle épuisé"})
                continue
            t0 = horloge()
            resume["appels"] += 1
            try:
                resp = client.system_one(state=item["state"], questions=questions, model=MODELE,
                                         timeout=config.JEV_TIMEOUT_SEC)
                ligne.update(_lire_reponse(resp, item))
                resume["ok"] += 1
            except Exception as e:
                resume["erreurs"] += 1
                ligne.update(statut="erreur", erreur=f"{type(e).__name__}: {str(e)[:200]}")
                logger.warning(f"Jev {item['ticker']} : {ligne['erreur']}")
            ligne["latence_ms"] = int((horloge() - t0) * 1000)
            _enregistrer(ligne)
        if resume["ecartes"]:
            logger.warning(f"Jev : budget {config.JEV_BUDGET_SEC:.0f} s épuisé, "
                           f"{len(resume['ecartes'])} actif(s) écarté(s) : {', '.join(resume['ecartes'])}")
        logger.info(f"Jev : {resume['ok']} observation(s), {resume['erreurs']} erreur(s), "
                    f"{len(resume['ecartes'])} écarté(s)")
    except Exception as e:
        logger.error(f"Jev : observation interrompue, cycle non affecté ({e})")
    return resume
