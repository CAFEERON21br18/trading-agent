"""
rejeu/rapport.py — Le rapport du rejeu : reports/rejeu/RAPPORT.md (hors git).

Tout est relu dans le grand livre du rejeu (rejeu/etude.py) : le rapport et la page /pro/rejeu
donnent les mêmes chiffres. Sections : (1) le verdict, critère appliqué mot pour mot, les trois
conditions une à une ; (2) un tableau par année pour la configuration qui décide ; (3) la
sensibilité aux frais et au capital ; (4) les limites ; (5) le nombre de trades par année.
Les hypothèses de frais sont écrites en tête. Rien n'est ajusté pour améliorer le résultat.
"""

import os

from rejeu import etude, rapport_limites
from rejeu import parametres as P
from rejeu import texte as T

AVERTISSEMENT = (
    "> **Hypothèses de frais.** Profil « CFD » : écart de 0,10 % par côté sur les actions et les ETF, de 0,50 % sur\n"
    "> les cryptos (et, faute de consigne, sur les contrats à terme), financement de 0,02 % par nuit sur le montant\n"
    "> de la position. Ce sont des **HYPOTHÈSES**, à remplacer par des écarts mesurés sur un compte démo.\n"
    "> Profil « Revolut » : 1 € par ordre, valeur observée sur un relevé, à confirmer contre la grille tarifaire.\n"
    ">\n"
    "> Simulation sur des cours passés, en paper trading : aucun ordre réel, et rien ici n'est un conseil\n"
    "> d'investissement. Un résultat passé ne dit pas le résultat futur.")


def libelle(e) -> str:
    return f"{T.nombre(e.capital, 0)}{T.ESPACE}€ · {P.PROFILS[e.profil]['libelle']}"


def section_verdict(e) -> str:
    lignes = [f"## 1. Verdict\n\n**Verdict : « {e.verdict} ».**\n",
              f"Configuration qui décide : capital de {T.nombre(e.capital, 0)} €, profil de frais "
              f"« {P.PROFILS[e.profil]['libelle']} », années {P.ANNEES[0]} à {P.ANNEES[-1]}, "
              f"**{e.periode.trades} trades clos**. Critère : `docs/REGISTRE_CRITERES.md` §10, écrit avant le premier "
              "lancement. « Utile » si les trois conditions sont vraies, sinon « sans avantage » ; moins de "
              f"{P.MIN_TRADES} trades clos sur la période : « non décidable ».\n"]
    for c in e.conditions:
        lignes.append(f"{c.numero}. **{c.titre} : {T.oui_non(c.vraie)}.** {c.constat[0].upper()}{c.constat[1:]}.")
    lignes.append(f"\nLes autres configurations sont des mesures de sensibilité : elles ne fondent pas le verdict.")
    return "\n".join(lignes)


def _ligne_annee(nom: str, b, reference, ecart) -> list[str]:
    return [nom, str(b.trades), T.eur(b.resultat_net), T.eur(b.esperance), T.intervalle(b.intervalle),
            T.pct(b.taux_reussite, signe=False), T.ratio(b.profit_factor), T.pct(b.part_frais, signe=False),
            T.pct(b.drawdown_max), T.pct(b.rendement), T.pct(reference.rendement), T.pct(ecart)]


def section_annees(e) -> str:
    entetes = ["Année", "Trades clos", "Résultat net", "Espérance nette", "Intervalle à 95 %", "Réussite",
               "Profit factor", "Part des frais", "Drawdown max", "Rendement", "Référence annuelle", "Écart"]
    lignes = [_ligne_annee(f"{a.numero}{' (partielle, à part)' if a.partielle else ''}", a.strategie, a.reference,
                           a.ecart) for a in e.annees]
    lignes.append(_ligne_annee(f"**{P.ANNEES[0]}–{P.ANNEES[-1]}**", e.periode, e.reference_annuelle, e.ecart_annuelle))
    return (f"## 2. Année par année — {libelle(e)}\n\n" + T.tableau(entetes, lignes) + "\n\n"
            "Un trade compte dans l'année de sa clôture. Rendement et drawdown : sur la valeur du compte à la clôture "
            "de chaque jour (résultat latent compris). Référence annuelle : le même univers à parts égales, acheté le "
            "premier jour de bourse de l'année, vendu le dernier, mêmes frais, même capital. Rendement annualisé sur "
            f"{P.ANNEES[0]}–{P.ANNEES[-1]} : stratégie {T.pct(e.periode.rendement_annualise)}, référence rachetée chaque "
            f"année {T.pct(e.reference_annuelle.rendement_annualise)}, référence gardée sur la période "
            f"{T.pct(e.reference_periode.rendement_annualise)} (drawdown maximal : {T.pct(e.periode.drawdown_max)}, "
            f"{T.pct(e.reference_annuelle.drawdown_max)} et {T.pct(e.reference_periode.drawdown_max)}).")


def section_sensibilite(etudes: list, resume: dict) -> str:
    entetes = ["Capital · frais", "Trades clos", "Résultat net", "Frais payés", "Espérance nette", "Intervalle à 95 %",
               "Réussite", "Profit factor", "Drawdown max", "Rendement annualisé", "Rendement / drawdown",
               "Réf. annuelle", "Réf. période", "Verdict"]
    lignes = []
    for e in etudes:
        p = e.periode
        lignes.append([libelle(e) + (" **(décide)**" if e.decide else ""), str(p.trades), T.eur(p.resultat_net),
                       T.montant(p.frais), T.eur(p.esperance), T.intervalle(p.intervalle),
                       T.pct(p.taux_reussite, signe=False), T.ratio(p.profit_factor), T.pct(p.drawdown_max),
                       T.pct(p.rendement_annualise), T.ratio(p.ratio), T.ratio(e.reference_annuelle.ratio),
                       T.ratio(e.reference_periode.ratio), e.verdict + ("" if e.decide else " (indicatif)")])
    memes = ("Les trades sont les mêmes d'un profil de frais à l'autre : l'agent ne compte aucun frais, seul le "
             "résultat net change." if resume.get("memes_trades_entre_profils") else
             "ATTENTION : les trades diffèrent d'un profil de frais à l'autre, ce qui ne devrait pas arriver.")
    return (f"## 3. Sensibilité aux frais et au capital ({P.ANNEES[0]}–{P.ANNEES[-1]})\n\n" + T.tableau(entetes, lignes)
            + "\n\n« Réf. annuelle » et « Réf. période » : rendement annualisé divisé par le drawdown maximal des deux "
            "références « acheter et garder », à comparer à la colonne « Rendement / drawdown ». " + memes)


def composer(etudes: list, resume: dict) -> str:
    decide = next(e for e in etudes if e.decide)
    d = resume.get("durees_s", {})
    tete = (f"# Rejeu sur plusieurs années du cœur technique — rapport\n\n"
            f"Lancement du {resume.get('lance_le', '?')} · commit `{resume.get('commit')}` · {len(resume.get('titres', []))} "
            f"titres · barres jusqu'au {resume.get('derniere_barre')} · empreinte des barres "
            f"`{str(resume.get('empreinte_barres'))[:16]}` · durée {d.get('total', '?')} s "
            f"(analyses {d.get('analyses', '?')} s, simulations {d.get('simulations', '?')} s).\n\n{AVERTISSEMENT}")
    return "\n\n".join([tete, section_verdict(decide), section_annees(decide), section_sensibilite(etudes, resume),
                        rapport_limites.section_limites(decide, etudes, resume),
                        rapport_limites.section_trades(etudes, resume)]) + "\n"


def ecrire(dossier: str | None = None, dossier_rapport: str | None = None, resume: dict | None = None) -> str:
    """Écrit RAPPORT.md à partir du grand livre du rejeu. Rend son chemin."""
    etudes = etude.lire(dossier)
    chemin = os.path.join(dossier_rapport or P.DOSSIER_RAPPORT, "RAPPORT.md")
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write(composer(etudes, resume or {}))
    return chemin
