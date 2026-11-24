"""
dashboard/pro/synchro.py — Ce que fait le bouton « Synchroniser » du dashboard professionnel.

Dans l'ordre : les positions paper de la base de l'agent (importeurs/paper.py), puis les taux
EURUSD quotidiens (importeurs/taux_change.py), en mode appliquer. Les deux écritures sont
validées ensemble : si la colonne « boucle » manque, si une position est illisible, si le
cours est indisponible ou si une erreur survient, RIEN n'est écrit et le message est rendu
tel quel. Tout ce qui peut échouer sans écrire est donc fait d'abord : lecture des positions,
répétition à blanc dans un grand livre en mémoire, téléchargement des cours.
Sans Flask. Aucune tâche planifiée ne passe par ici : c'est une action de Lucia.
"""

from dataclasses import asdict
from datetime import date, datetime, timezone

import ledger
from importeurs import paper
from importeurs import taux_change as tc


def _echec(message: str) -> dict:
    return {"ok": False, "message": message}


def _positions_illisibles(erreurs: list) -> str:
    return ("positions illisibles, rien n'a été écrit : "
            + " ; ".join(f"position #{pos_id} : {raison}" for pos_id, raison in erreurs))


def _periode_des_taux(chemin_ledger: str, vide, aujourd_hui: date) -> tuple[date, date]:
    """Période par défaut de l'importeur de taux, lue sans écrire (grand livre absent : 365 jours)."""
    lecture = ledger.ouvrir_lecture(chemin_ledger)
    try:
        return tc.periode_par_defaut(lecture if lecture is not None else vide, aujourd_hui)
    finally:
        if lecture is not None:
            lecture.close()


def synchroniser(chemin_ledger: str, chemin_base: str, telecharger=None,
                 aujourd_hui: date | None = None) -> dict:
    """Synchronise et rend {"ok": True, "paper": …, "taux": …}, ou {"ok": False, "message": …}."""
    aujourd_hui = aujourd_hui or datetime.now(timezone.utc).date()
    telecharger = telecharger or tc.cloture_yfinance
    essai = ledger.ouvrir(":memory:")  # jamais écrit sur le disque
    try:
        # 1. positions lisibles, colonne « boucle » présente, aucune position illisible
        repetition = paper.synchroniser(essai, chemin_base, appliquer=False)
        if repetition.erreurs:
            return _echec(_positions_illisibles(repetition.erreurs))
        # 2. cours téléchargés avant toute écriture
        debut, fin = _periode_des_taux(chemin_ledger, essai, aujourd_hui)
        cours = list(telecharger(debut, fin))
    except (paper.SynchronisationImpossible, tc.SourceIndisponible) as exc:
        return _echec(str(exc))
    finally:
        essai.close()
    # 3. les deux écritures dans une seule transaction du grand livre
    try:
        conn = ledger.ouvrir(chemin_ledger)
    except Exception as exc:
        return _echec(f"grand livre impossible à ouvrir ({type(exc).__name__} : {exc}). Rien n'a été écrit.")
    try:
        r_paper = paper.synchroniser(conn, chemin_base, appliquer=True, valider=False)
        if r_paper.erreurs:  # la base a changé depuis la répétition
            conn.rollback()
            return _echec(_positions_illisibles(r_paper.erreurs))
        r_taux = tc.importer(conn, debut, fin, telecharger=lambda d, f: cours,
                             aujourd_hui=aujourd_hui, appliquer=True, valider=False)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _echec(f"{type(exc).__name__} : {exc}. Rien n'a été écrit.")
    finally:
        conn.close()
    taux = asdict(r_taux)
    taux.update(ecartes=len(r_taux.ecartes),
                premier=r_taux.premier.isoformat() if r_taux.premier else None,
                dernier=r_taux.dernier.isoformat() if r_taux.dernier else None)
    return {"ok": True, "paper": asdict(r_paper), "taux": taux}
