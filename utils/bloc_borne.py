"""
utils/bloc_borne.py — Bloc facultatif ajouté à un cycle : jamais d'exception vers le cycle, temps borné.

Pour les ajouts placés APRÈS les décisions, ouvertures, fermetures et le traitement Jev d'un cycle
(cadre de la session du 17/10/2026, règle 4). executer_borne lance la fonction dans un fil (daemon)
et l'attend au plus budget_s secondes :
- exception → journalisée, résultat `defaut` ;
- budget dépassé → journalisé, le cycle continue sans attendre (le fil s'arrête avec le processus) ;
- sinon → la valeur rendue par la fonction.
lancer_blocs fait de même pour une liste (nom, module, fonction, budget en s) : l'import du
module se fait dans le fil, donc un import cassé ou lent est borné lui aussi.
executer_en_parallele lance plusieurs lectures à la fois (vue temps réel du dashboard).
"""

import importlib
import threading
import time

from utils.logger import get_logger

logger = get_logger(__name__)


def executer_borne(nom: str, fonction, budget_s: float, *args, defaut=None, **kwargs):
    """Résultat de fonction(*args, **kwargs), ou `defaut` en cas d'erreur ou de dépassement."""
    resultat: dict = {}

    def cible():
        try:
            resultat["valeur"] = fonction(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 — rien ne doit remonter vers le cycle
            resultat["erreur"] = e

    try:
        fil = threading.Thread(target=cible, name=f"bloc {nom}", daemon=True)
        fil.start()
        fil.join(budget_s)
    except Exception as e:
        logger.error(f"{nom} : lancement impossible ({e}) ; le cycle continue")
        return defaut
    if fil.is_alive():
        logger.warning(f"{nom} : budget de {budget_s:g} s dépassé ; le cycle continue sans attendre")
        return defaut
    if "erreur" in resultat:
        logger.error(f"{nom} échoué ({type(resultat['erreur']).__name__} : {resultat['erreur']}) ; "
                     f"le cycle continue")
        return defaut
    return resultat.get("valeur", defaut)


def _appeler(module: str, fonction: str):
    return getattr(importlib.import_module(module), fonction)()


def lancer_blocs(blocs) -> None:
    """Lance chaque (nom, module, fonction, budget en s), l'un après l'autre ; ne lève jamais."""
    for nom, module, fonction, budget in blocs:
        try:
            executer_borne(nom, _appeler, budget, module, fonction)
        except Exception as e:
            logger.error(f"{nom} : {e} (le cycle continue)")


def executer_en_parallele(budgets: dict, appels: dict) -> dict:
    """{nom: résultat, ou None si l'appel échoue ou dépasse budgets[nom] secondes} ; les appels
    tournent en même temps (fils daemon), aucune exception ne sort."""
    resultats, fils, debut = {}, {}, time.monotonic()
    for nom, appel in appels.items():
        def cible(n=nom, f=appel):
            try:
                resultats[n] = f()
            except Exception as e:
                logger.warning(f"{n} : {type(e).__name__} {e}")
        fils[nom] = threading.Thread(target=cible, name=f"lecture {nom}", daemon=True)
        fils[nom].start()
    for nom, fil in fils.items():
        fil.join(max(0.0, debut + budgets[nom] - time.monotonic()))  # échéances parallèles
        if fil.is_alive():
            logger.warning(f"{nom} : budget de {budgets[nom]:g} s dépassé, lecture ignorée")
    return {nom: resultats.get(nom) for nom in appels}
