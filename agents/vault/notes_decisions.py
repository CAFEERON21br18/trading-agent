"""
agents/vault/notes_decisions.py — 10-Decisions et 20-Actifs de la mémoire de trading (Phase 2, partie A).

10-Decisions : une note par décision BUY ou SELL, regroupée par (actif, jour de Lisbonne, action),
l'unité que le registre compte (« couples, jamais des lignes », REGISTRE_CRITERES v1.7) : le tactical
répète la même décision toutes les 15 minutes, chaque passage reste une ligne de la note.
Liens [[actif]] et [[Cycle AAAA-MM-JJ]] (cycle du jour). Pas de HOLD ni de NO_TRADE.
20-Actifs : une note par actif de la watchlist (dernière enregistrée dans le registre), avec ses
dernières décisions et ses positions paper.
"""

from collections import Counter, defaultdict

from agents.vault.ecriture import AVERTISSEMENT, cellule, frontmatter, lien, nom_fichier, prix

DOSSIER_DECISIONS, DOSSIER_ACTIFS = "10-Decisions", "20-Actifs"
DERNIERES = 15
SUITES = {"ouverte": "ouverte", "refusee": "refusée", "sans_donnees": "sans données de prix",
          "non_traitee": "non traitée", "erreur_execution": "erreur d'exécution"}


def nom_decision(jour, ticker, decision) -> str:
    return f"{jour} {ticker} {decision}"


def nom_cycle(jour) -> str:
    return f"Cycle {jour}"


def nom_position(p) -> str:
    return f"Position {p['id']} {p['ticker']}"


def grouper(decisions) -> dict:
    """{(jour, ticker, décision): [passages dans l'ordre]}."""
    groupes = defaultdict(list)
    for d in decisions:
        groupes[(d["jour"], d["ticker"], d["decision"])].append(d)
    return dict(groupes)


def _bornes(valeurs, forme) -> str:
    if not valeurs:
        return "—"
    bas, haut = forme.format(min(valeurs)), forme.format(max(valeurs))
    return bas if bas == haut else f"{bas} à {haut}"


def _resume(lignes) -> str:
    suites = Counter(SUITES.get(l["resultat"], l["resultat"] or "?") for l in lignes)
    return ", ".join(f"{n} {s}" for s, n in suites.most_common())


def note_decision(cle, lignes, positions_par_id) -> str:
    jour, ticker, decision = cle
    cycles = Counter(l["cycle"] for l in lignes)
    scores = [l["score"] for l in lignes if l["score"] is not None]
    confiances = [l["confiance"] for l in lignes if l["confiance"] is not None]
    ouvertes = sorted({l["position_id"] for l in lignes if l["resultat"] == "ouverte" and l["position_id"]})
    tags = ["decision", decision.lower()] + [l["cycle"] for l in lignes]
    tags += ["ouverte"] if ouvertes else []
    tags += ["sans-donnees"] if any(l["resultat"] == "sans_donnees" for l in lignes) else []
    texte = [frontmatter(jour, "decision", ticker, cycles, decision, tags),
             f"# {ticker} — {decision} — {jour[8:]}/{jour[5:7]}/{jour[:4]}\n",
             f"{lien(ticker)} · {lien(nom_cycle(jour))} (cycle du jour)\n",
             f"- Passages : {len(lignes)} ({', '.join(f'{c} ×{n}' for c, n in sorted(cycles.items()))}), "
             f"de {lignes[0]['heure']} à {lignes[-1]['heure']} (heure de Lisbonne)",
             f"- Score : {_bornes(scores, '{:+.2f}')}",
             f"- Confiance : {_bornes(confiances, '{}')}/10",
             f"- Suite : {_resume(lignes)}"]
    for pid in ouvertes:
        p = positions_par_id.get(pid)
        texte.append(f"- Position ouverte : {lien(nom_position(p)) if p and p['sortie'] else f'n° {pid} (en cours)'}")
    texte += ["", "| Heure | Cycle | Style | Score | Conf. | Prix | Pipeline | Suite | Raisons |",
              "|---|---|---|---|---|---|---|---|---|"]
    for l in lignes:
        texte.append("| " + " | ".join(cellule(v) for v in (
            l["heure"], l["cycle"], l["style"], None if l["score"] is None else f"{l['score']:+.2f}",
            l["confiance"], prix(l["prix"]), l["pipeline"],
            SUITES.get(l["resultat"], l["resultat"]), "; ".join(l["raisons"])[:160] or None)) + " |")
    texte += ["", AVERTISSEMENT, ""]
    return "\n".join(texte)


def notes_decisions(groupes, positions) -> dict:
    par_id = {p["id"]: p for p in positions}
    return {f"{DOSSIER_DECISIONS}/{nom_fichier(nom_decision(*cle))}.md": note_decision(cle, lignes, par_id)
            for cle, lignes in groupes.items()}


def _ligne_position(p) -> str:
    entree = f"entrée le {p['entree']:%d/%m %H:%M} à {prix(p['entry_price'])}" if p["entree"] else "entrée —"
    if p["sortie"] is None:
        return (f"- n° {p['id']} {p['direction']} — {entree}, investi {p['invested_amount']:.2f} €, "
                f"stop {prix(p['stop_loss'])}, objectif {prix(p['target_1'])} (ouverte)")
    pnl = f"{p['pnl_percent']:+.2f} %" if p["pnl_percent"] is not None else "—"
    return f"- {lien(nom_position(p))} {p['direction']} — {entree}, sortie le {p['sortie']:%d/%m %H:%M}, {pnl}"


def notes_actifs(watchlist, groupes, positions) -> dict:
    notes = {}
    for categorie, tickers in watchlist:
        for ticker in tickers:
            cles = sorted((c for c in groupes if c[1] == ticker), reverse=True)
            siennes = [p for p in positions if p["ticker"] == ticker]
            jours = [c[0] for c in cles] + [(p["sortie"] or p["entree"]).date().isoformat()
                                            for p in siennes if p["sortie"] or p["entree"]]
            texte = [frontmatter(max(jours) if jours else None, "actif", ticker, (),
                                 cles[0][2] if cles else None, ["actif", categorie]),
                     f"# {ticker}\n", f"Catégorie de la watchlist : {categorie}\n",
                     f"## Dernières décisions BUY / SELL ({min(DERNIERES, len(cles))} sur {len(cles)} jours-actions)\n"]
            texte += [f"- {lien(nom_decision(*c))} — {len(groupes[c])} passage(s), {_resume(groupes[c])}"
                      for c in cles[:DERNIERES]] or ["_Aucune depuis le 06/10/2026._"]
            texte += ["", "## Positions paper\n"]
            texte += [_ligne_position(p) for p in sorted(siennes, key=lambda p: p["id"], reverse=True)] \
                or ["_Aucune depuis le 06/10/2026._"]
            texte += ["", AVERTISSEMENT, ""]
            notes[f"{DOSSIER_ACTIFS}/{nom_fichier(ticker)}.md"] = "\n".join(texte)
    return notes
