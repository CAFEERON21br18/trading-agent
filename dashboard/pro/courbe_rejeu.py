"""
dashboard/pro/courbe_rejeu.py — Valeur du compte du rejeu et de ses références, sur un même graphique.

Écrit côté serveur, comme la courbe de la page « Vue d'ensemble » : aucun script, aucun appel
externe, et aucun texte dans le dessin (il s'étire à la largeur de la page). Les textes sont du
HTML, chacun dans sa zone : la légende au-dessus, les graduations à gauche, les dates dessous.
Les courbes se distinguent par leur TRAIT (plein, tirets, pointillé), nommé dans la légende, et
pas par la couleur seule. L'axe horizontal suit le temps ; un point par semaine suffit au dessin.
"""

from html import escape

from dashboard.pro import formats
from dashboard.pro.courbe_svg import GRILLE, HAUTEUR, ZERO, graduations

TRAITS = [("plein", "", "#38bdf8"), ("tirets", "7 5", "#fbbf24"), ("pointillé", "2 4", "#e2e8f0")]
PAS = 5  # un point sur cinq (une semaine de bourse) ; le dernier point est toujours gardé


def _allegee(serie: list) -> list:
    return [p for i, p in enumerate(serie) if i % PAS == 0 or i == len(serie) - 1]


def courbe(series: list[tuple[str, list]], devise: str, titre: str) -> str:
    """HTML du graphique. series : (libellé, [(jour, valeur)]) ; trois au plus, la première en trait plein.
    Chaîne vide s'il n'y a pas au moins deux jours à tracer."""
    series = [(nom, _allegee(points)) for nom, points in series if len(points) >= 2][:len(TRAITS)]
    if not series:
        return ""
    jours = [j for _, points in series for j, _ in points]
    valeurs = [v for _, points in series for _, v in points]
    debut, fin = min(jours), max(jours)
    axe = graduations(min(valeurs), max(valeurs))
    haut, etendue, duree = axe[0], axe[0] - axe[-1], max(1, (fin - debut).days)
    fixe = 'vector-effect="non-scaling-stroke"'
    dessin = [f'<line x1="0" x2="100" y1="{float((haut - g) / etendue) * 100:.2f}" y2="{float((haut - g) / etendue) * 100:.2f}" '
              f'stroke="{ZERO if g == 0 else GRILLE}" stroke-width="1" {fixe}/>' for g in axe]
    legende = []
    for (nom, points), (trait, tirets, couleur) in zip(series, TRAITS):
        trace = " ".join(f"{(j - debut).days / duree * 100:.2f},{float((haut - v) / etendue) * 100:.2f}" for j, v in points)
        pointille = f' stroke-dasharray="{tirets}"' if tirets else ""
        dessin.append(f'<polyline points="{trace}" fill="none" stroke="{couleur}" stroke-width="2"{pointille} '
                      f'stroke-linejoin="round" {fixe}/>')
        legende.append(
            '<span class="inline-flex items-start gap-1">'  # le libellé peut passer à la ligne sur téléphone
            f'<svg viewBox="0 0 28 6" class="w-7 h-1.5 shrink-0 mt-1.5" aria-hidden="true"><line x1="0" x2="28" y1="3" y2="3" '
            f'stroke="{couleur}" stroke-width="2"{pointille}/></svg>'
            f'<span>{escape(nom)} (trait {trait}) : <span class="text-slate-200 whitespace-nowrap">'
            f"{escape(formats.montant(points[-1][1], devise))}</span></span></span>")
    resume = f"{titre}. " + " ; ".join(
        f"{nom} : {formats.montant(points[-1][1], devise)} au {formats.jour(points[-1][0])}" for nom, points in series)
    echelle = "".join(
        f'<span class="absolute right-2 whitespace-nowrap" style="top:{float((haut - g) / etendue) * 100:.2f}%;'
        f'transform:translateY(-50%)">{escape("0" if g == 0 else formats.montant(g, devise).replace(",00", ""))}</span>'
        for g in axe)
    return (
        f'<figure class="m-0" role="img" aria-label="{escape(resume, quote=True)}">'
        f'<figcaption class="flex flex-wrap gap-x-4 gap-y-1 mb-4 text-xs text-slate-400">{"".join(legende)}</figcaption>'
        '<div class="flex">'
        f'<div data-axe="y" class="relative shrink-0 w-[5rem] {HAUTEUR} text-[11px] leading-none text-slate-400">{echelle}</div>'
        '<div class="flex-1 min-w-0 px-1">'
        f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" class="block w-full {HAUTEUR} '
        f'overflow-visible">{"".join(dessin)}</svg>'
        '<div data-axe="x" class="flex justify-between mt-3 text-[11px] leading-none text-slate-400">'
        f"<span>{escape(formats.jour(debut))}</span><span>{escape(formats.jour(fin))}</span></div></div></div></figure>")
