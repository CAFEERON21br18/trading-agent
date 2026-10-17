"""
utils/bloc_borne.py — Bloc facultatif ajouté à un cycle : jamais d'exception vers le cycle, temps borné.

Pour les ajouts placés APRÈS les décisions, ouvertures, fermetures et le traitement Jev d'un cycle
(cadre de la session du 17/10/2026, règle 4). executer_borne lance la fonction dans un fil (daemon)
et l'attend au plus budget_s secondes :
- exception → journalisée, résultat `defaut` ;
- budget dépassé → journalisé, le cycle continue sans attendre (le fil s'arrête avec le processus) ;
- sinon → la valeur rendue par la fonction.
"""

import threading

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
