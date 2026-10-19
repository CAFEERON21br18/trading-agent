"""
scripts/sync_vault_trading.py — Mémoire de trading dans le vault Obsidian (Phase 2, partie A).

LIT data/registre.db et data/database.db (mode=ro, jamais une table real_*) et memory/intuition_log.md,
puis écrit des notes Markdown dans le vault :
  00-Index.md      note d'entrée
  10-Decisions/    une note par décision BUY ou SELL (actif, jour, action), liens [[actif]] et [[Cycle …]]
  20-Actifs/       une note par actif de la watchlist : dernières décisions, positions paper
  30-Intuitions/   entrées de intuition_log.md où l'intuition a modifié la décision
  40-Cycles/       une note par jour : résumé du quotidien, et de la semaine le dimanche
  50-Positions/    une note par position paper fermée : entrée, sortie, motif
Chaque passage reconstruit tout depuis R2 (06/10/2026) : le premier crée l'historique, les suivants ne
réécrivent que les notes qui changent (noms déterministes, écriture atomique, aucun doublon). Les notes
sans la ligne « genere_par: sync_vault_trading » (écrites à la main) ne sont jamais touchées.
Ne touche ni au Decision Engine ni aux cycles de décision.
Vault : ALPHASIGNAL_VAULT (environnement ou .env), sinon %USERPROFILE%\\Documents\\AlphaSignalVault.

Usage : .venv\\Scripts\\python.exe scripts\\sync_vault_trading.py [--vault DOSSIER]
Lancé à la fin du cycle quotidien du matin (scripts/cycle_daily.py, BLOCS_DE_FIN, budget de 120 s).
"""

import argparse
import os
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from utils.logger import get_logger

logger = get_logger(__name__)

INTUITIONS = os.path.join(RACINE, "memory", "intuition_log.md")
HEURE_LIMITE = 12  # passage du matin seulement (7h30, rattrapé dans la matinée), heure de Lisbonne


def construire_notes(registre: dict, paper: dict, texte_intuitions: str) -> dict:
    """{chemin relatif dans le vault: contenu} pour toutes les notes générées."""
    from agents.vault import index, notes_cycles, notes_decisions, notes_positions

    groupes = notes_decisions.grouper(registre["decisions"])
    intuitions = notes_positions.notes_intuitions(texte_intuitions, groupes)
    notes = {}
    notes.update(notes_decisions.notes_decisions(groupes, paper["positions"]))
    notes.update(notes_decisions.notes_actifs(registre["watchlist"], groupes, paper["positions"]))
    notes.update(intuitions)
    notes.update(notes_cycles.notes_cycles(registre, paper, groupes))
    notes.update(notes_positions.notes_positions(paper["positions"], groupes))
    notes[index.FICHIER_INDEX] = index.note_index(registre, paper, groupes, len(intuitions))
    return notes


def synchroniser(vault: str | None = None, chemin_registre: str | None = None, chemin_base: str | None = None,
                 chemin_intuitions: str = INTUITIONS) -> dict:
    """Lit les bases, écrit les notes ; rend le bilan {ecrites, inchangees, manuelles, notes, vault}."""
    from agents.vault import lecture
    from agents.vault.ecriture import ecrire_notes
    from utils.vault_chemin import dossier_vault

    registre = lecture.lire_registre(chemin_registre or lecture.REGISTRE)
    paper = lecture.lire_paper(chemin_base or lecture.BASE)
    try:
        with open(chemin_intuitions, encoding="utf-8") as f:
            texte_intuitions = f.read()
    except OSError:
        texte_intuitions = ""
    notes = construire_notes(registre, paper, texte_intuitions)
    cible = vault or dossier_vault()
    bilan = ecrire_notes(cible, notes)
    bilan.update(notes=len(notes), vault=cible)
    logger.info(f"Vault de trading : {bilan['notes']} notes, {bilan['ecrites']} écrite(s), "
                f"{bilan['inchangees']} inchangée(s), {len(bilan['manuelles'])} manuelle(s) laissée(s) ({cible})")
    return bilan


def synchroniser_du_matin(maintenant: datetime | None = None) -> dict | None:
    """Bloc de fin du cycle quotidien : seulement le passage du matin (avant HEURE_LIMITE, Lisbonne)."""
    from agents.vault.lecture import _fuseau

    heure = (maintenant or datetime.now(_fuseau())).astimezone(_fuseau()).hour
    if heure >= HEURE_LIMITE:
        logger.info(f"Vault de trading : passage de {heure} h, synchronisé seulement le matin")
        return None
    return synchroniser()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--vault", help="dossier racine du vault (défaut : ALPHASIGNAL_VAULT ou Documents)")
    args = parser.parse_args()
    try:
        bilan = synchroniser(vault=args.vault)
    except Exception as e:
        print(f"Échec : {e}", file=sys.stderr)
        return 1
    print(f"{bilan['notes']} notes dans {bilan['vault']} : {bilan['ecrites']} écrite(s), "
          f"{bilan['inchangees']} inchangée(s), {len(bilan['manuelles'])} note(s) manuelle(s) laissée(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
