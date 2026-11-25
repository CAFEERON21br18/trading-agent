"""
dashboard/pro/rejeu_vue.py — Contenu de la page « Rejeu » (/pro/rejeu).

LECTURE SEULE du grand livre du rejeu (data/rejeu/ledger_rejeu.db, jamais data/ledger.db) et du
résumé du dernier lancement (data/rejeu/lancement.json). La page ne lance rien : le rejeu se
lance à la main (scripts/rejeu.py). Les chiffres viennent de rejeu/etude.py, comme ceux du
rapport : mêmes mesures, même verdict. Le verdict affiché en tête est toujours celui de la
configuration du critère (1 000 €, « Revolut ») ; les autres ne sont que des mesures de
sensibilité. Sans Flask. Le calcul (bootstrap compris) est gardé en mémoire tant que le fichier
du grand livre ne change pas.
"""

import json
import os

from dashboard.pro import courbe_rejeu
from rejeu import etude, grand_livre
from rejeu import parametres as P
from rejeu import texte as T
from rejeu.resultat import REFERENCE_ANNUELLE, REFERENCE_PERIODE, STRATEGIE

MENTIONS = [
    ("Hypothèses de frais CFD", "écart de 0,10 % par côté sur les actions et les ETF, de 0,50 % sur les cryptos et les "
     "contrats à terme, financement de 0,02 % par nuit : des hypothèses, à remplacer par des écarts mesurés sur un "
     "compte démo. Le profil « Revolut » (1 € par ordre) vient d'un relevé et reste à confirmer."),
    ("Biais de sélection", "l'univers est la liste de 2026, des titres choisis après coup et qui ont souvent "
     "fortement monté. Cela flatte la stratégie comme la référence."),
    ("Ce que le rejeu teste", "le seul analyste technique, sur des barres quotidiennes ; fondamental, sentiment, "
     "mémoire et intuition sont neutres. Simulation sur des cours passés : aucun ordre réel, pas un conseil."),
]
_memoire: dict = {}


def _etude(dossier: str, capital: int, profil: str):
    chemin = grand_livre.chemin(dossier)
    etat = (os.path.getmtime(chemin), os.path.getsize(chemin))
    if _memoire.get("etat") != (chemin, etat):
        _memoire.clear()
        _memoire["etat"] = (chemin, etat)
    if (capital, profil) not in _memoire:
        _memoire[(capital, profil)] = etude.lire(dossier, [(capital, profil)])[0]
    return _memoire[(capital, profil)]


def _lancement(dossier: str) -> dict:
    try:
        with open(os.path.join(dossier, "lancement.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _libelle(capital: int, profil: str) -> str:
    return f"{T.nombre(capital, 0)}{T.ESPACE}€ · {P.PROFILS[profil]['libelle']}"


def _ligne(nom: str, b, reference, ecart) -> dict:
    return {"annee": nom, "trades": b.trades, "net": T.eur(b.resultat_net), "positif": (b.resultat_net or 0) > 0,
            "negatif": (b.resultat_net or 0) < 0, "esperance": T.eur(b.esperance), "intervalle": T.intervalle(b.intervalle),
            "reussite": T.pct(b.taux_reussite, signe=False), "profit_factor": T.ratio(b.profit_factor),
            "part_frais": T.pct(b.part_frais, signe=False), "drawdown": T.pct(b.drawdown_max),
            "rendement": T.pct(b.rendement), "reference": T.pct(reference.rendement), "ecart": T.pct(ecart)}


def page_sans_resultat() -> dict:
    """Contexte sans aucun chiffre : rejeu jamais lancé, ou lecture en échec. Les mentions y sont."""
    return {"lance": False, "mentions": MENTIONS, "seuil": P.MIN_TRADES, "annees": f"{P.ANNEES[0]}–{P.ANNEES[-1]}"}


def page(capital: int, profil: str, dossier: str | None = None) -> dict:
    """Contexte du gabarit pro_rejeu.html. `lance` faux : le rejeu n'a jamais tourné sur cette machine."""
    dossier = dossier or P.DOSSIER
    contexte = page_sans_resultat()
    if not os.path.isfile(grand_livre.chemin(dossier)):
        return contexte
    if (capital, profil) not in [(c, p) for c in P.CAPITAUX for p in P.PROFILS]:
        capital, profil = P.CONFIG_QUI_DECIDE
    decide, choisie = _etude(dossier, *P.CONFIG_QUI_DECIDE), _etude(dossier, capital, profil)
    resume = _lancement(dossier)
    p = choisie.periode
    series = [("Stratégie", choisie.courbes[STRATEGIE]), ("Référence rachetée chaque année", choisie.courbes[REFERENCE_ANNUELLE]),
              ("Référence gardée sur la période", choisie.courbes[REFERENCE_PERIODE])]
    lignes = [_ligne(f"{a.numero}{' (partielle, à part)' if a.partielle else ''}", a.strategie, a.reference, a.ecart)
              for a in choisie.annees]
    lignes.append(_ligne(contexte["annees"], p, choisie.reference_annuelle, choisie.ecart_annuelle))
    contexte.update(
        lance=True, verdict=decide.verdict, trades_decide=decide.periode.trades,
        conditions=[{"numero": c.numero, "titre": c.titre, "vraie": c.vraie, "constat": c.constat} for c in decide.conditions],
        libelle_decide=_libelle(*P.CONFIG_QUI_DECIDE), libelle=_libelle(capital, profil), est_decide=choisie.decide,
        verdict_indicatif=choisie.verdict,
        conditions_indicatives=[{"numero": c.numero, "vraie": c.vraie, "constat": c.constat} for c in choisie.conditions],
        configurations=[{"capital": c, "profil": pr, "libelle": _libelle(c, pr), "choisie": (c, pr) == (capital, profil),
                         "decide": (c, pr) == P.CONFIG_QUI_DECIDE} for c in P.CAPITAUX for pr in P.PROFILS],
        lignes=lignes,
        chiffres=[("Trades clos", str(p.trades)), ("Résultat net", T.eur(p.resultat_net)), ("Frais payés", T.montant(p.frais)),
                  ("Rendement annualisé", T.pct(p.rendement_annualise)), ("Drawdown maximal", T.pct(p.drawdown_max)),
                  ("Rendement / drawdown", T.ratio(p.ratio)),
                  ("Réf. annuelle, même ratio", T.ratio(choisie.reference_annuelle.ratio)),
                  ("Réf. période, même ratio", T.ratio(choisie.reference_periode.ratio))],
        courbe=courbe_rejeu.courbe(series, P.DEVISE, f"Valeur du compte, {_libelle(capital, profil)}"),
        ouvertes=choisie.ouvertes, sorties=choisie.sorties,
        lance_le=str(resume.get("lance_le", "")), derniere_barre=resume.get("derniere_barre"),
        titres=len(resume.get("titres", [])), ecartes=sorted(resume.get("ecartes") or {}),
        duree=(resume.get("durees_s") or {}).get("total"), code_inchange=resume.get("code_agent_inchange"),
        erreurs=sum(c.get("erreurs_agent", 0) for c in resume.get("configurations", [])),
    )
    return contexte
