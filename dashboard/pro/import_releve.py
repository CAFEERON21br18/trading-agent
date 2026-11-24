"""
dashboard/pro/import_releve.py — Import du relevé CSV Revolut depuis la page « Mes trades ».

Deux temps, sans Flask ici :
- apercu() lit le relevé en mémoire et le compare au grand livre ouvert en lecture seule :
  rien n'est écrit, ni dans le grand livre ni sur le disque ;
- confirmer() écrit, par importeurs/revolut_csv.py et donc par ledger/ecriture.py seulement.
  L'import est tout ou rien : une erreur et rien n'est écrit.
Le relevé n'est jamais enregistré dans un fichier, et rien de son contenu ne va dans les journaux.
"""

import io

import ledger
from importeurs import revolut_csv

TAILLE_MAX = 2 * 1024 * 1024  # 2 Mo


class ReleveRefuse(ValueError):
    """Le fichier envoyé n'est pas un relevé lisible : message affiché tel quel."""


def decoder(octets: bytes) -> str:
    """Texte du relevé. Refuse un fichier vide, trop gros ou qui n'est pas du texte UTF-8."""
    if len(octets) > TAILLE_MAX:
        raise ReleveRefuse("fichier trop volumineux : 2 Mo au plus")
    if not octets.strip():
        raise ReleveRefuse("fichier vide")
    try:
        return octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ReleveRefuse("le fichier n'est pas un texte UTF-8 : exporter le relevé en CSV") from None


def _resume(rapport: revolut_csv.Rapport) -> dict:
    return {
        "trades_a_ajouter": rapport.importes, "trades_deja_presents": rapport.deja_presents,
        "mouvements_a_ajouter": rapport.mouvements_importes,
        "mouvements_deja_presents": rapport.mouvements_deja_presents,
        "ignores": dict(sorted(rapport.ignores.items())),
        "erreurs": [[numero, message] for numero, message in rapport.erreurs],
    }


def apercu(texte: str, chemin_ledger: str) -> dict:
    """Ce qu'un import ajouterait. Le grand livre n'est ni créé ni modifié."""
    conn = ledger.ouvrir_lecture(chemin_ledger)
    try:
        resume = _resume(revolut_csv.apercu(conn, io.StringIO(texte, newline="")))
    finally:
        if conn is not None:
            conn.close()
    resume["a_ajouter"] = resume["trades_a_ajouter"] + resume["mouvements_a_ajouter"]
    resume["confirmable"] = not resume["erreurs"] and resume["a_ajouter"] > 0
    return resume


def confirmer(texte: str, chemin_ledger: str) -> dict:
    """Écrit le relevé dans le grand livre (créé s'il n'existe pas). Une erreur : rien n'est écrit,
    et le grand livre n'est même pas ouvert."""
    _, _, lecture = revolut_csv.lire(io.StringIO(texte, newline=""))
    if lecture.erreurs:
        return dict(_resume(lecture), ecrit=False)
    conn = ledger.ouvrir(chemin_ledger)
    try:
        resume = _resume(revolut_csv.importer_flux(conn, io.StringIO(texte, newline="")))
    finally:
        conn.close()
    resume["ecrit"] = not resume["erreurs"]
    return resume
