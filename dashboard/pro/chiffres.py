"""
dashboard/pro/chiffres.py — Les cinq chiffres d'un panneau de la page « Vue d'ensemble ».

Résultat net réalisé, résultat latent, total des frais et leur part du résultat brut,
espérance en R, taux de réussite. Sous chaque chiffre : le nombre de trades qui le portent
et, sous le seuil du socle (100), le badge « non décidable · n / 100 ». Une mesure non
calculable s'écrit « — », jamais 0 ; sans taux de change, « taux indisponible ».
Sans Flask : des dictionnaires de textes déjà mis en forme, que le gabarit échappe.
"""

import mesures
from dashboard.pro import donnees, formats, latent


def pluriel(n: int, mot: str) -> str:
    return f"{n} {mot}{'s' if n > 1 else ''}"


def badge(n: int) -> str:
    """Sous 100 trades, la mesure est affichée mais ne prouve rien."""
    return "" if n >= mesures.MIN_TRADES else f"non décidable · {n} / {mesures.MIN_TRADES}"


def chiffre(libelle: str, texte: str, detail: str = "", badge: str = "", classe: str = "",
            note: str = "") -> dict:
    return {"libelle": libelle, "texte": texte, "detail": detail, "badge": badge,
            "classe": classe, "note": note}


def _mesure(tableau: donnees.Bloc, nom: str, libelle: str, forme, suite: str = "") -> dict:
    if tableau.indisponible:
        return chiffre(libelle, tableau.indisponible)
    m = tableau.valeur[nom]
    return chiffre(libelle, forme(m.valeur), pluriel(m.n, "trade") + suite, badge(m.n),
                   formats.classe(m.valeur) if forme is not formats.pourcent else "")


def _latent(l: latent.Latent, devise: str) -> dict:
    libelle = "Résultat latent"
    if not l.lignes:
        return chiffre(libelle, formats.ABSENT, "aucune position ouverte")
    detail = f"{pluriel(l.valorisees, 'position')} sur {len(l.lignes)} avec un prix"
    note = (f"{pluriel(l.sans_prix, 'position')} en « prix indisponible », hors du total"
            if l.sans_prix else "")
    if l.indisponible:
        return chiffre(libelle, l.indisponible, detail, note=note)
    return chiffre(libelle, formats.montant_signe(l.total, devise), detail,
                   classe=formats.classe(l.total), note=note)


def _frais(frais: donnees.Bloc, tableau: donnees.Bloc, devise: str) -> dict:
    libelle = "Total des frais"
    if tableau.indisponible:
        part, marque = f"part du résultat brut : {tableau.indisponible}", ""
    else:
        m = tableau.valeur["part des coûts"]
        part = f"part du résultat brut : {formats.pourcent(m.valeur)} ({pluriel(m.n, 'trade')} clos)"
        marque = badge(m.n)
    if frais.indisponible:
        return chiffre(libelle, frais.indisponible, badge=marque, note=part)
    f = frais.valeur
    if f.ordres_avec_frais == 0:  # aucun frais enregistré n'est pas « 0 € de frais », ni « 0 % »
        return chiffre(libelle, formats.ABSENT, f"aucun frais enregistré sur {pluriel(f.ordres, 'ordre')}",
                       note=f"part du résultat brut : {formats.ABSENT}")
    return chiffre(libelle, formats.montant(f.total, devise),
                   f"{pluriel(f.ordres_avec_frais, 'ordre')} avec frais sur {f.ordres}", marque, note=part)


def cinq_chiffres(source: donnees.Source, devise: str, periode: str, valeur_latente: latent.Latent) -> list[dict]:
    """Les cinq chiffres du panneau, dans l'ordre d'affichage."""
    tableau = donnees.tableau_mesures(source, devise, periode)

    def argent(valeur):
        return formats.montant_signe(valeur, devise)

    return [
        _mesure(tableau, "résultat net", "Résultat net réalisé", argent),
        _latent(valeur_latente, devise),
        _frais(donnees.total_frais(source, devise, periode), tableau, devise),
        _mesure(tableau, "espérance en R", "Espérance en R", formats.en_r, " avec stop connu"),
        _mesure(tableau, "taux de réussite", "Taux de réussite", formats.pourcent),
    ]


def mouvement(bloc: donnees.Bloc, libelle: str, devise: str) -> dict:
    """Apports nets ou dividendes du panneau réel : une somme de faits, sans badge."""
    if bloc.indisponible:
        return chiffre(libelle, bloc.indisponible)
    m = bloc.valeur
    return chiffre(libelle, formats.montant_signe(m.valeur, devise), pluriel(m.n, "mouvement"),
                   classe=formats.classe(m.valeur))
