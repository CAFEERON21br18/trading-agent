"""
agents/vault/notes_cycles.py — 40-Cycles de la mémoire de trading (Phase 2, partie A).

Une note par jour (Lisbonne) depuis R2 : résumé du cycle quotidien (passage enregistré dans le
registre, instantané du portefeuille paper, ancre du registre), passages des autres cycles,
décisions BUY / SELL et positions du jour ; le dimanche, la semaine (positions fermées sur 7 jours,
comme le rapport hebdomadaire). Tout vient des bases : les rapports Markdown restent dans reports/.
"""

from collections import Counter
from datetime import date, timedelta

from agents.vault.ecriture import AVERTISSEMENT, frontmatter, lien, nom_fichier
from agents.vault.notes_decisions import nom_cycle, nom_decision, nom_position

DOSSIER_CYCLES = "40-Cycles"


def _jour(d) -> str:
    return d.date().isoformat() if d else ""


def _fr(jour: str) -> str:
    return f"{jour[8:]}/{jour[5:7]}/{jour[:4]}"


def _quotidien(jour, passages, instantane, ancre) -> list:
    lignes = [f"- Passage de {p['heure']} : {p['ecrites']} décision(s) écrite(s) dans le registre, "
              f"{p['erreurs']} erreur(s), {p['duree_s'] or 0:.0f} s" for p in passages if p["cycle"] == "quotidien"]
    lignes = lignes or ["- Aucun passage quotidien enregistré ce jour."]
    if instantane:
        i = instantane
        lignes.append(f"- Portefeuille paper : valeur {i['total_value']:.2f} €, cash {i['cash']:.2f} €, investi "
                      f"{i['invested']:.2f} €, {i['open_positions_count']} position(s) ouverte(s), jour "
                      f"{i['daily_return_percent'] or 0:+.2f} %, cumul {i['cumulative_return_percent'] or 0:+.2f} %")
    if ancre:
        lignes.append(f"- Ancre du registre : empreinte {ancre['empreinte']}…, {ancre['lignes']} ligne(s), "
                      f"{ancre['erreurs']} erreur(s) à la vérification")
    lignes.append(f"- Rapport complet : reports/daily/report_{jour}.md (dépôt de la tour)")
    return lignes


def _semaine(jour, positions) -> list:
    fin = date.fromisoformat(jour)
    jours = {(fin - timedelta(days=k)).isoformat() for k in range(7)}
    fermees = [p for p in positions if _jour(p["sortie"]) in jours]
    gagnantes = sum(1 for p in fermees if (p["pnl_euros"] or 0) > 0)
    pnl = sum(p["pnl_euros"] or 0 for p in fermees)
    annee, semaine, _ = fin.isocalendar()
    taux = f"{gagnantes / len(fermees) * 100:.1f} %" if fermees else "—"
    return ["", "## Hebdomadaire\n",
            f"- Positions fermées du {_fr(min(jours))} au {_fr(jour)} : {len(fermees)} "
            f"({gagnantes} gagnante(s), {len(fermees) - gagnantes} perdante(s)), taux {taux}",
            f"- P&L paper de la semaine : {pnl:+.2f} €",
            f"- Rapport hebdomadaire : reports/weekly/week_{annee}_W{semaine:02d}.md (dépôt de la tour)"]


def notes_cycles(registre, paper, groupes) -> dict:
    passages_par_jour = {}
    for p in registre["passages"]:
        passages_par_jour.setdefault(p["jour"], []).append(p)
    jours = sorted(set(passages_par_jour) | {c[0] for c in groupes})
    notes = {}
    for jour in jours:
        passages = passages_par_jour.get(jour, [])
        par_cycle = Counter(p["cycle"] for p in passages)
        dimanche = date.fromisoformat(jour).weekday() == 6
        decisions = sorted(c for c in groupes if c[0] == jour)
        ouvertes = [p for p in paper["positions"] if _jour(p["entree"]) == jour]
        fermees = [p for p in paper["positions"] if _jour(p["sortie"]) == jour]
        texte = [frontmatter(jour, "cycle", None, par_cycle, None, ["cycle"] + (["hebdo"] if dimanche else [])),
                 f"# Cycle du {_fr(jour)}\n", "## Quotidien\n"]
        texte += _quotidien(jour, passages, paper["instantanes"].get(jour), registre["ancres"].get(jour))
        texte += ["", f"Passages enregistrés : {', '.join(f'{c} ×{n}' for c, n in sorted(par_cycle.items())) or 'aucun'}",
                  "", f"## Décisions BUY / SELL du jour ({len(decisions)})\n"]
        texte += [f"- {lien(nom_decision(*c))} — {len(groupes[c])} passage(s)" for c in decisions] or ["_Aucune._"]
        texte += ["", "## Positions paper du jour\n"]
        texte += [f"- Ouverte : {lien(nom_position(p)) if p['sortie'] else 'n° ' + str(p['id'])} "
                  f"{lien(p['ticker'])} {p['direction']} à {p['entree']:%H:%M}" for p in ouvertes]
        texte += [f"- Fermée : {lien(nom_position(p))} ({p['status']}, {p['pnl_percent'] or 0:+.2f} %)" for p in fermees]
        texte += [] if ouvertes or fermees else ["_Aucune ouverture ni fermeture._"]
        texte += _semaine(jour, paper["positions"]) if dimanche else []
        texte += ["", AVERTISSEMENT, ""]
        notes[f"{DOSSIER_CYCLES}/{nom_fichier(nom_cycle(jour))}.md"] = "\n".join(texte)
    return notes
