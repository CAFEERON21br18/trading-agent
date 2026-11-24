"""
rejeu/rapport_limites.py — Sections 4 et 5 du rapport du rejeu : les limites, puis le nombre de
trades par année, les sorties, les refus, les données et les entrées neutralisées.
"""

from rejeu import parametres as P
from rejeu import texte as T


def _config(resume: dict, e) -> dict:
    return next((c for c in resume.get("configurations", []) if (c["capital"], c["profil"]) == (e.capital, e.profil)), {})


def section_limites(decide, etudes: list, resume: dict) -> str:
    ecartes = resume.get("ecartes") or {}
    sans_trade = [f"{T.nombre(e.capital, 0)} €" for e in etudes if e.periode.trades == 0 and e.profil == "revolut"]
    points = [
        "**Biais de sélection.** L'univers est la liste de 2026 : des titres choisis après coup, dont beaucoup ont "
        "fortement monté depuis 2018. Aucun titre disparu ou délaissé n'y figure. Cela flatte la stratégie comme la "
        "référence, et rien ne dit que la liste de demain se comportera de même.",
        "**Analystes neutralisés.** Seul l'analyste technique décide. Entrées neutres ou absentes : "
        + " ; ".join(f"{nom} ({effet})" for nom, effet in resume.get("neutralisees", [])) + ".",
        "**Frais CFD supposés.** Les écarts et le financement du profil « CFD » sont des hypothèses, pas des mesures. "
        "Le profil « Revolut » (1 € par ordre) vient d'un relevé et reste à confirmer.",
        "**Barres quotidiennes seulement.** Une décision par jour à la clôture, exécutée à l'ouverture suivante. "
        "L'agent réel décide aussi toutes les 15 minutes et entre au prix du moment. Dans une barre, on ne sait pas "
        "si le stop ou l'objectif a été touché d'abord : le stop est pris. Ni glissement, ni carnet d'ordres.",
        "**Ventes à découvert.** L'agent décide SELL comme BUY, et le rejeu garde les deux. Un compte d'actions au "
        "comptant ne vend pas à découvert : le profil « Revolut » est un barème de frais, pas un compte.",
        "**Change.** Comme le paper trader, le rejeu compte 1 € = 1 $ : capital en euros, cours en dollars.",
        f"**Réglages du code, pas ceux de la tour.** {P.CONFIG_AGENT['MAX_POSITIONS_SIMULTANEES']} positions "
        "simultanées (défaut de `config.py`) ; le `.env` de la tour en porte 20. Le capital de l'agent reste constant : "
        "il ne suit pas le résultat, comme en production.",
        f"**Positions encore ouvertes.** {decide.ouvertes} position(s) ouverte(s) à la dernière barre "
        f"({resume.get('derniere_barre')}) : dans la valeur du compte, pas dans les trades clos.",
    ]
    if ecartes:
        points.append("**Titres écartés pour données inutilisables** (stratégie et référence) : "
                      + " ; ".join(f"{t} ({', '.join(r)})" for t, r in sorted(ecartes.items())) + ".")
    if sans_trade:
        points.append(f"**Capital de {', '.join(sans_trade)} : aucun trade.** Le Budget Manager plafonne un trade à "
                      "10 % du cash investissable et refuse tout budget sous 15 € : la mesure de sensibilité est vide.")
    if resume.get("code_agent_inchange") is False:
        points.append("**Code de l'agent modifié depuis le critère.** Le rejeu ne teste plus exactement « les règles "
                      "telles qu'elles sont au commit de la section 10 ».")
    erreurs = sum(c.get("erreurs_agent", 0) for c in resume.get("configurations", []))
    if erreurs:
        points.append(f"**Erreurs journalisées par l'agent pendant le rejeu : {erreurs}.** À lire dans "
                      "`data/rejeu/lancement.json` avant de se fier au résultat.")
    return "## 4. Limites\n\n" + "\n".join(f"- {p}" for p in points)


def section_trades(etudes: list, resume: dict) -> str:
    annees = [a.numero for a in etudes[0].annees]
    lignes = [[f"{T.nombre(e.capital, 0)}{T.ESPACE}€ · {P.PROFILS[e.profil]['libelle']}" + (" **(décide)**" if e.decide else "")]
              + [str(a.strategie.trades) for a in e.annees] + [str(e.periode.trades)] for e in etudes]
    entetes = ["Configuration"] + [str(a) + (" (partielle)" if a not in P.ANNEES else "") for a in annees] \
        + [f"{P.ANNEES[0]}–{P.ANNEES[-1]}"]
    decide = next(e for e in etudes if e.decide)
    config = _config(resume, decide)
    sorties = " ; ".join(f"{motif} : {n}" for motif, n in decide.sorties.items()) or "aucune"
    decisions = " ; ".join(f"{d} : {n}" for d, n in (config.get("decisions") or {}).items()) or "non disponible"
    refus = " ; ".join(f"« {motif} » : {n}" for motif, n in list((config.get("refus") or {}).items())[:8]) or "aucun"
    controles = resume.get("controles") or {}
    donnees = T.tableau(["Titre", "Barres", "Première", "Dernière", "Sans prix", "Doublons", "Trous"],
                        [[t, str(c["barres"]), c["premiere"], c["derniere"], str(c["sans_prix"]), str(c["doublons"]),
                          str(c["trous"])] for t, c in controles.items()]) if controles else "Non disponible."
    return (f"## 5. Nombre de trades clos par année\n\n" + T.tableau(entetes, lignes) + "\n\n"
            f"Configuration qui décide — sorties par motif : {sorties}. Décisions du moteur sur toute la série : "
            f"{decisions}. Ouvertures refusées par le circuit de l'agent : {refus}.\n\n"
            f"### Données\n\n{donnees}\n\n"
            f"### Paramètres\n\nGraine du bootstrap : {P.GRAINE} ; tirages : {T.nombre(P.TIRAGES, 0)} ; "
            f"réglages de l'agent : {', '.join(f'{k} = {v}' for k, v in P.CONFIG_AGENT.items())} ; seuils de décision : "
            f"{P.SEUIL_BUY} et {P.SEUIL_SELL}. Tous les paramètres : `rejeu/parametres.py`.")
