"""
agents/vault/ecriture.py — Notes de la mémoire de trading : frontmatter, liens, écriture atomique (Phase 2).

- Frontmatter YAML normalisé, mêmes clés dans toutes les notes : date, type, actif, cycle (liste),
  decision, tags (liste), puis le MARQUEUR (comme scripts/sync_graphify_vault.py).
- Noms de fichiers déterministes : relancer ne crée aucun doublon ; une note n'est réécrite que si
  son contenu change (fichier temporaire du même dossier, puis os.replace : jamais à moitié écrite).
- Une note sans MARQUEUR (écrite à la main, ou dont on a retiré la ligne pour la garder) n'est
  jamais modifiée. Aucune note n'est supprimée.
"""

import json
import os
import re

MARQUEUR = "genere_par: sync_vault_trading"
_INTERDITS = re.compile(r'[\\/:*?"<>|#^\[\]]')  # Windows + liens Obsidian (# titre, ^ bloc, | alias)
AVERTISSEMENT = "⚠️ Paper trading uniquement : aucun ordre réel, pas un conseil financier."


def nom_fichier(texte: str) -> str:
    return _INTERDITS.sub("_", str(texte)).strip() or "_"


def lien(nom: str, texte: str | None = None) -> str:
    """[[nom]] vers une note ; alias quand le nom de fichier diffère du texte affiché."""
    fichier = nom_fichier(nom)
    affiche = texte if texte is not None else nom
    return f"[[{fichier}]]" if affiche == fichier else f"[[{fichier}|{_INTERDITS.sub('_', affiche)}]]"


def frontmatter(date, type_note, actif=None, cycles=(), decision=None, tags=()) -> str:
    valeurs = [("date", date or "null"), ("type", json.dumps(type_note)),
               ("actif", json.dumps(actif) if actif else "null"),
               ("cycle", json.dumps(sorted(set(cycles)), ensure_ascii=False)),
               ("decision", json.dumps(decision) if decision else "null"),
               ("tags", json.dumps([t for t in dict.fromkeys(tags) if t], ensure_ascii=False))]
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in valeurs) + MARQUEUR + "\n---\n"


def prix(valeur) -> str:
    """Prix lisible : six chiffres significatifs, jamais de notation scientifique au-delà de 1e6."""
    if valeur is None:
        return "—"
    return f"{valeur:.2f}" if abs(valeur) >= 1e6 else f"{valeur:.6g}"


def cellule(valeur) -> str:
    """Valeur pour une table Markdown (| échappé, pas de retour à la ligne)."""
    if valeur is None:
        return "—"
    return str(valeur).replace("|", "\\|").replace("\n", " ")


def est_generee(chemin: str) -> bool:
    try:
        with open(chemin, encoding="utf-8") as f:
            return MARQUEUR in f.read(800)
    except OSError:
        return False


def ecrire_notes(vault: str, notes: dict) -> dict:
    """notes : {chemin relatif au vault: contenu}. Rend {ecrites, inchangees, manuelles}."""
    bilan = {"ecrites": 0, "inchangees": 0, "manuelles": []}
    for relatif, contenu in sorted(notes.items()):
        chemin = os.path.join(vault, relatif)
        if os.path.exists(chemin):
            if not est_generee(chemin):
                bilan["manuelles"].append(relatif)
                continue
            with open(chemin, encoding="utf-8", newline="") as f:
                if f.read() == contenu:
                    bilan["inchangees"] += 1
                    continue
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        temporaire = os.path.join(os.path.dirname(chemin), f".{os.path.basename(chemin)}.tmp")
        try:
            with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
                f.write(contenu)
            os.replace(temporaire, chemin)
        finally:
            if os.path.exists(temporaire):
                os.remove(temporaire)
        bilan["ecrites"] += 1
    return bilan
