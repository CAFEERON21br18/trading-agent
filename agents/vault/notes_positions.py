"""
agents/vault/notes_positions.py — 50-Positions et 30-Intuitions de la mémoire de trading (Phase 2, partie A).

50-Positions : une note par position paper fermée depuis R2 (entrée, sortie, motif, résultat), liée
à son actif, à la décision du jour d'entrée et aux cycles d'entrée et de sortie. Les post-mortems
viendront plus tard, dans des notes écrites à la main (jamais touchées par la synchronisation).
30-Intuitions : miroir de memory/intuition_log.md, seulement les entrées où l'intuition a modifié
la décision (ligne « **Override** ») ; le fichier n'est que lu.
"""

import re

from agents.vault.ecriture import AVERTISSEMENT, frontmatter, lien, nom_fichier, prix
from agents.vault.lecture import DEBUT
from agents.vault.notes_decisions import nom_cycle, nom_decision, nom_position

DOSSIER_POSITIONS, DOSSIER_INTUITIONS = "50-Positions", "30-Intuitions"
_TITRE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC — (.+?) — (\S+) \(intuition\)\s*$", re.M)
_n = lambda v, f=None: prix(v) if f is None or v is None else format(v, f)


def notes_positions(positions, groupes) -> dict:
    notes = {}
    for p in positions:
        if p["sortie"] is None or p["sortie"].date().isoformat() < DEBUT:
            continue
        action = "BUY" if p["direction"] == "LONG" else "SELL"
        jour_e = p["entree"].date().isoformat() if p["entree"] else None
        jour_s = p["sortie"].date().isoformat()
        resultat = "gagnante" if (p["pnl_euros"] or 0) > 0 else "perdante"
        liens = [lien(p["ticker"]), f"sortie {lien(nom_cycle(jour_s))}"]
        if jour_e and jour_e >= DEBUT:  # pas de note de cycle avant R2
            liens.append(f"entrée {lien(nom_cycle(jour_e))}")
        if (jour_e, p["ticker"], action) in groupes:
            liens.append(f"décision {lien(nom_decision(jour_e, p['ticker'], action))}")
        duree = p["sortie"] - p["entree"] if p["entree"] else None
        texte = [frontmatter(jour_s, "position", p["ticker"], (), action, ["position", p["status"].lower(), resultat]),
                 f"# Position {p['id']} — {p['ticker']} {p['direction']} ({resultat})\n", " · ".join(liens) + "\n",
                 "## Entrée\n",
                 f"- {p['entree']:%d/%m/%Y %H:%M} (Lisbonne) à {_n(p['entry_price'])}, quantité {_n(p['quantity'], '.6g')}, "
                 f"investi {_n(p['invested_amount'], '.2f')} €" if p["entree"] else "- Date d'entrée inconnue",
                 f"- Stop {_n(p['stop_loss'])}, objectif {_n(p['target_1'])}, confiance {p['confidence'] or '—'}/10",
                 f"- Raison : {p['entry_reason'] or '—'}", "", "## Sortie\n",
                 f"- {p['sortie']:%d/%m/%Y %H:%M} (Lisbonne) à {_n(p['exit_price'])} — {p['status']}",
                 f"- Motif : {p['exit_reason'] or '—'}",
                 f"- Résultat : {_n(p['pnl_euros'], '+.2f')} € ({_n(p['pnl_percent'], '+.2f')} %)"
                 + (f", durée {duree.days} j {duree.seconds // 3600} h {duree.seconds % 3600 // 60} min" if duree else ""),
                 "", AVERTISSEMENT, ""]
        notes[f"{DOSSIER_POSITIONS}/{nom_fichier(nom_position(p))}.md"] = "\n".join(texte)
    return notes


def entrees_intuition(texte: str) -> list:
    """[(jour, heure 'HHMM', ticker, décision, bloc)] des entrées où l'intuition a modifié la décision."""
    titres = list(_TITRE.finditer(texte or ""))
    sortie = []
    for i, m in enumerate(titres):
        bloc = texte[m.start(): titres[i + 1].start() if i + 1 < len(titres) else len(texte)].strip()
        if "**Override**" in bloc:
            sortie.append((m.group(1), m.group(2) + m.group(3), m.group(4).strip(), m.group(5), bloc))
    return sortie


def notes_intuitions(texte: str, groupes) -> dict:
    notes = {}
    for jour, heure, ticker, decision, bloc in entrees_intuition(texte):
        nom = f"Intuition {jour} {heure} {ticker}"
        liens = [lien(ticker), lien(nom_cycle(jour))]
        if (jour, ticker, decision) in groupes:
            liens.append(lien(nom_decision(jour, ticker, decision)))
        corps = "\n".join(l for l in bloc.splitlines()[1:])
        notes[f"{DOSSIER_INTUITIONS}/{nom_fichier(nom)}.md"] = "\n".join([
            frontmatter(jour, "intuition", ticker, (), decision, ["intuition", "override"]),
            f"# Intuition — {ticker} — {decision} ({jour}, {heure[:2]}:{heure[2:]} UTC)\n",
            " · ".join(liens) + "\n", "Entrée de memory/intuition_log.md :\n", corps, "", AVERTISSEMENT, ""])
    return notes
