"""
dashboard/pro/courbe_svg.py — Courbe du résultat net réalisé cumulé, écrite côté serveur.

Aucune bibliothèque de graphiques, aucun script, aucun appel à un CDN. Chart.js n'est présent
dans le dashboard que par un CDN (base.html) ; la consigne des pages l'écarte. Une courbe par
compte, jamais deux comptes sur le même graphique.

Le dessin (SVG) ne contient AUCUN texte : il s'étire à la largeur de la page, et du texte dessiné
dedans rétrécirait avec lui sur un téléphone. Tous les textes sont du HTML, chacun dans sa zone :
- au-dessus, la ligne « plus haut », « plus bas », « dernier » ;
- à gauche, la colonne des graduations de l'axe vertical ;
- en dessous du dessin, les dates du premier et du dernier jour.
Ces zones ne se chevauchent pas : les libellés « plus haut » et « plus bas » ne peuvent pas
recouvrir une graduation, à largeur de téléphone comme sur grand écran. Les valeurs écrites
portent leur signe ; la couleur ne dit rien de plus.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from html import escape

from dashboard.pro import formats

JOURS_MINIMUM = 2  # en dessous, pas de graphique : la page écrit une phrase
TRAIT = "#38bdf8"  # même bleu quel que soit le signe
GRILLE, ZERO = "#334155", "#94a3b8"
HAUTEUR = "h-44"  # hauteur du dessin et de la colonne des graduations (classes Tailwind)


def _pas(etendue: Decimal) -> Decimal:
    """Écart « rond » entre deux graduations (1, 2 ou 5 fois une puissance de 10), pour 4 intervalles environ."""
    if etendue <= 0:
        return Decimal(1)
    brut = etendue / 4
    base = Decimal(1).scaleb(brut.adjusted())
    return next(base * m for m in (1, 2, 5, 10) if base * m >= brut)


def graduations(bas: Decimal, haut: Decimal) -> list[Decimal]:
    """Graduations de l'axe vertical, de la plus haute à la plus basse. Elles encadrent les
    valeurs et contiennent toujours le zéro."""
    bas, haut = min(bas, Decimal(0)), max(haut, Decimal(0))
    pas = _pas(haut - bas)
    premier = int((bas / pas).to_integral_value(ROUND_FLOOR))
    dernier = max(int((haut / pas).to_integral_value(ROUND_CEILING)), premier + 1)
    return [pas * k for k in range(dernier, premier - 1, -1)]


def _libelle(valeur: Decimal, decimales: int, devise: str) -> str:
    if valeur == 0:
        return "0"
    signe = "+" if valeur > 0 else formats.MOINS
    return f"{signe}{formats.nombre(valeur, decimales)}{formats.ESPACE}{formats.SYMBOLES.get(devise, devise)}"


def courbe(serie: list, devise: str, titre: str) -> str:
    """HTML de la courbe de la série (jour, cumul). Moins de deux jours de clôture : chaîne vide,
    la page écrit une phrase à la place.

    L'axe horizontal suit l'ordre des jours de clôture, pas leur écart en temps : un point par
    jour où un trade s'est clos. La ligne pointillée est le zéro.
    """
    if len(serie) < JOURS_MINIMUM:
        return ""
    valeurs = [v for _, v in serie]
    axe = graduations(min(valeurs), max(valeurs))
    haut, etendue = axe[0], axe[0] - axe[-1]
    decimales = 0 if axe[0] - axe[1] >= 1 else 2

    def y(valeur) -> float:
        return float((haut - valeur) / etendue) * 100

    def argent(valeur) -> str:
        return escape(formats.montant_signe(valeur, devise))

    dernier_jour, dernier = serie[-1]
    resume = (f"{titre} : {formats.montant_signe(dernier, devise)} au {formats.jour(dernier_jour)}, "
              f"plus haut {formats.montant_signe(max(valeurs), devise)}, "
              f"plus bas {formats.montant_signe(min(valeurs), devise)}, {len(serie)} jours de clôture")
    points = [(100 * i / (len(serie) - 1), y(v)) for i, v in enumerate(valeurs)]
    fixe = 'vector-effect="non-scaling-stroke"'
    trait_du_zero = f'stroke="{ZERO}" stroke-dasharray="4 4"'
    dessin = [f'<line x1="0" x2="100" y1="{y(g):.2f}" y2="{y(g):.2f}" stroke-width="1" '
              + (trait_du_zero if g == 0 else f'stroke="{GRILLE}"') + f" {fixe}/>" for g in axe]
    trace = " ".join(f"{x:.2f},{py:.2f}" for x, py in points)
    dessin.append(f'<polyline points="{trace}" fill="none" stroke="{TRAIT}" stroke-width="2" '
                  f'stroke-linejoin="round" stroke-linecap="round" {fixe}/>')
    dessin += [f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{py:.2f}" y2="{py:.2f}" stroke="{TRAIT}" stroke-width="6" '
               f'stroke-linecap="round" {fixe}/>' for x, py in points]
    echelle = "".join(
        f'<span class="absolute right-2 whitespace-nowrap" style="top:{y(g):.2f}%;transform:translateY(-50%)">'
        f"{escape(_libelle(g, decimales, devise))}</span>" for g in axe)
    return (
        f'<figure class="m-0" role="img" aria-label="{escape(resume, quote=True)}">'
        '<figcaption class="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-4 text-xs text-slate-400">'
        f'<span data-libelle="haut">plus haut <span class="text-slate-200">{argent(max(valeurs))}</span></span>'
        f'<span data-libelle="bas">plus bas <span class="text-slate-200">{argent(min(valeurs))}</span></span>'
        f'<span class="ml-auto text-sm font-semibold text-slate-100">dernier {argent(dernier)}</span>'
        "</figcaption>"
        '<div class="flex">'
        f'<div data-axe="y" class="relative shrink-0 w-[4.5rem] {HAUTEUR} text-[11px] leading-none text-slate-400">'
        f"{echelle}</div>"
        '<div class="flex-1 min-w-0 px-1">'
        f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" '
        f'class="block w-full {HAUTEUR} overflow-visible">{"".join(dessin)}</svg>'
        '<div data-axe="x" class="flex justify-between mt-3 text-[11px] leading-none text-slate-400">'
        f"<span>{escape(formats.jour(serie[0][0]))}</span><span>{escape(formats.jour(dernier_jour))}</span>"
        "</div></div></div></figure>"
    )
