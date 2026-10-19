"""
agents/vault/index.py — 00-Index, note d'entrée de la mémoire de trading (Phase 2, partie A).

Liens vers les derniers cycles, la watchlist, les dernières décisions et positions, les intuitions
et la carte du code (90-Graphify). Contenu déterministe : aucune heure de génération, seulement
l'heure de la dernière ligne lue dans le registre, pour que relancer ne réécrive rien sans raison.
"""

from agents.vault.ecriture import AVERTISSEMENT, MARQUEUR, frontmatter, lien
from agents.vault.lecture import DEBUT
from agents.vault.notes_decisions import nom_cycle, nom_decision, nom_position

FICHIER_INDEX = "00-Index.md"
RECENTS = 10


def note_index(registre, paper, groupes, nb_intuitions) -> str:
    jours = sorted({c[0] for c in groupes} | {p["jour"] for p in registre["passages"]}, reverse=True)
    fermees = sorted((p for p in paper["positions"] if p["sortie"] and p["sortie"].date().isoformat() >= DEBUT),
                     key=lambda p: p["sortie"], reverse=True)
    recentes = sorted(groupes, key=lambda c: (c[0], groupes[c][-1]["heure"]), reverse=True)
    texte = [frontmatter(jours[0] if jours else None, "index", None, (), None, ["index"]),
             "# AlphaSignal — mémoire de trading\n",
             f"Notes générées depuis data/registre.db et data/database.db (lecture seule) par "
             f"scripts/sync_vault_trading.py, chaque matin après le cycle quotidien. Historique depuis R2 "
             f"(06/10/2026) ; dernière ligne du registre lue : {registre['derniere'] or '—'} (Lisbonne).",
             "Aucune donnée du portefeuille réel.\n",
             f"## Derniers cycles\n"]
    texte += [f"- {lien(nom_cycle(j))}" for j in jours[:7]] or ["_Aucun._"]
    texte += ["", "## Watchlist\n"]
    texte += [f"- {categorie} : " + " · ".join(lien(t) for t in tickers) for categorie, tickers in registre["watchlist"]]
    texte += ["", f"## Dernières décisions BUY / SELL ({len(groupes)} jours-actions depuis R2)\n"]
    texte += [f"- {lien(nom_decision(*c))} — {len(groupes[c])} passage(s)" for c in recentes[:RECENTS]] or ["_Aucune._"]
    texte += ["", f"## Dernières positions paper fermées ({len(fermees)} depuis R2)\n"]
    texte += [f"- {lien(nom_position(p))} — {p['status']}, {p['pnl_percent'] or 0:+.2f} %" for p in fermees[:RECENTS]] \
        or ["_Aucune._"]
    texte += ["", "## Dossiers\n",
              "- 10-Decisions : une note par actif, jour et action (BUY ou SELL), chaque passage en ligne",
              "- 20-Actifs : une note par actif de la watchlist",
              f"- 30-Intuitions : décisions modifiées par l'intuition ({nb_intuitions} ; source "
              "memory/intuition_log.md)",
              "- 40-Cycles : une note par jour (quotidien, et hebdomadaire le dimanche)",
              "- 50-Positions : une note par position paper fermée",
              f"- 90-Graphify : carte du code, régénérée chaque dimanche ({lien('GRAPH_REPORT')})",
              "", "## Règles du vault\n",
              f"- Les notes générées portent « {MARQUEUR} » : elles sont réécrites à chaque passage.",
              "- Pour garder une note modifiée à la main, supprimez cette ligne : elle ne sera plus jamais touchée.",
              "- Les notes écrites à la main ne sont jamais modifiées ni supprimées.",
              "", AVERTISSEMENT, ""]
    return "\n".join(texte)
