"""
dashboard/pro/courbe_svg.py — Courbe du résultat net réalisé cumulé, dessinée en SVG côté serveur.

Aucune bibliothèque de graphiques, aucun script, aucun appel à un CDN : le dessin est du
texte SVG placé dans la page. Chart.js n'est présent dans le dashboard que par un CDN
(base.html) ; la consigne des pages l'écarte. Une courbe par compte, jamais deux comptes sur
le même graphique. Les valeurs écrites portent leur signe ; la couleur ne dit rien de plus.
"""

from html import escape

from dashboard.pro import formats

LARGEUR, HAUTEUR = 640, 220
MARGE_G, MARGE_D, MARGE_H, MARGE_B = 12, 12, 26, 30
TRAIT = "#38bdf8"  # même bleu quel que soit le signe


def _x(i: int, n: int) -> float:
    utile = LARGEUR - MARGE_G - MARGE_D
    return MARGE_G + (utile / 2 if n == 1 else utile * i / (n - 1))


def courbe(serie: list, devise: str, titre: str) -> str:
    """SVG de la série (jour, cumul). Série vide : chaîne vide, la page dit qu'il n'y a rien.

    L'axe horizontal suit l'ordre des jours de clôture, pas leur écart en temps : un point par
    jour où un trade s'est clos. La ligne pointillée est le zéro.
    """
    if not serie:
        return ""
    valeurs = [v for _, v in serie]
    haut, bas = max(max(valeurs), 0), min(min(valeurs), 0)
    etendue = (haut - bas) or 1
    utile = HAUTEUR - MARGE_H - MARGE_B

    def y(valeur) -> float:
        return MARGE_H + float((haut - valeur) / etendue) * utile

    points = [(_x(i, len(serie)), y(v)) for i, v in enumerate(valeurs)]
    trace = " ".join(f"{x:.1f},{py:.1f}" for x, py in points)
    dernier_jour, dernier = serie[-1]
    resume = (f"{titre} : {formats.montant_signe(dernier, devise)} au {formats.jour(dernier_jour)}, "
              f"plus haut {formats.montant_signe(max(valeurs), devise)}, "
              f"plus bas {formats.montant_signe(min(valeurs), devise)}, {len(serie)} jour(s) de clôture")
    texte = 'fill="#94a3b8" font-size="12"'
    parties = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LARGEUR} {HAUTEUR}" role="img" '
        f'aria-label="{escape(resume, quote=True)}" class="w-full h-auto">',
        f"<title>{escape(resume)}</title>",
        f'<line x1="{MARGE_G}" x2="{LARGEUR - MARGE_D}" y1="{y(0):.1f}" y2="{y(0):.1f}" '
        f'stroke="#64748b" stroke-width="1" stroke-dasharray="4 4"/>',
        f'<text x="{MARGE_G}" y="{y(0) - 4:.1f}" {texte}>0</text>',
        f'<polyline points="{trace}" fill="none" stroke="{TRAIT}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    parties += [f'<circle cx="{x:.1f}" cy="{py:.1f}" r="2.5" fill="{TRAIT}"/>' for x, py in points]
    parties += [
        f'<text x="{LARGEUR - MARGE_D}" y="16" text-anchor="end" fill="#e2e8f0" font-size="13" '
        f'font-weight="600">{escape(formats.montant_signe(dernier, devise))}</text>',
        f'<text x="{MARGE_G}" y="16" {texte}>plus haut {escape(formats.montant_signe(max(valeurs), devise))}'
        f" · plus bas {escape(formats.montant_signe(min(valeurs), devise))}</text>",
        f'<text x="{MARGE_G}" y="{HAUTEUR - 8}" {texte}>{escape(formats.jour(serie[0][0]))}</text>',
        f'<text x="{LARGEUR - MARGE_D}" y="{HAUTEUR - 8}" text-anchor="end" {texte}>'
        f"{escape(formats.jour(dernier_jour))}</text>",
        "</svg>",
    ]
    return "".join(parties)
