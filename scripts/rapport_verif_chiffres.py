"""
scripts/rapport_verif_chiffres.py — Chiffres des réponses LLM du chat absents du prompt (mode avertissement).

LECTURE SEULE : la base est ouverte en mode=ro, rien n'y est jamais écrit.
  python scripts/rapport_verif_chiffres.py           # 30 derniers jours, colonne verification_chiffres
  python scripts/rapport_verif_chiffres.py --passe   # recalcul sur toutes les réponses LLM + CSV d'étiquetage

Le CSV d'étiquetage va dans data/verif_chiffres/, ignoré par git (dépôt public :
les prompts contiennent le portefeuille réel ; le script refuse d'écrire sinon).
Colonne « vrai_ou_faux_positif » à remplir à la main.
"""

import os
import sys
import csv
import json
import argparse
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from agents.chat._verif_chiffres import classer, partie_prompt, references_du_prompt, verifier

JOURS, TOP, TAILLE_EXTRAIT = 30, 20, 80
DOSSIER_CSV = os.path.join(RACINE, "data", "verif_chiffres")
TRANCHES = ((0.0, "0 %"), (0.10, "]0 ; 10 %]"), (0.25, "]10 ; 25 %]"), (0.50, "]25 ; 50 %]"), (1.0, "> 50 %"))


def _connexion() -> sqlite3.Connection:
    from utils.database import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tranche(taux: float) -> str:
    return next(nom for borne, nom in TRANCHES if taux <= borne)


def extrait(texte: str, position: int, longueur: int, taille: int = TAILLE_EXTRAIT) -> str:
    """`taille` caractères centrés sur le chiffre, sur une seule ligne."""
    debut = max(0, position + longueur // 2 - taille // 2)
    return " ".join(texte[debut:debut + taille].split())


def statistiques(lignes: list[tuple]) -> dict:
    """lignes : (audit_id, message_utilisateur, vérification). Taux moyen sur les réponses
    qui contiennent au moins un chiffre vérifié (taux inconnu sinon, jamais compté 0)."""
    taux = [v["taux_non_soutenus"] for _, _, v in lignes if v.get("taux_non_soutenus") is not None]
    distribution = Counter(_tranche(t) for t in taux)
    distribution["sans chiffre vérifié"] = len(lignes) - len(taux)
    compte, origines = Counter(), {}
    for audit_id, message, v in lignes:
        for brut in v.get("non_soutenus") or []:
            compte[brut] += 1
            origines.setdefault(brut, []).append((audit_id, message))
    return {"messages": len(lignes), "avec_chiffres": len(taux),
            "taux_moyen": sum(taux) / len(taux) if taux else None,
            "chiffres": sum(v.get("nb_chiffres", 0) for _, _, v in lignes),
            "non_soutenus": sum(compte.values()), "distribution": distribution,
            "top": [(brut, n, origines[brut]) for brut, n in compte.most_common(TOP)]}


def afficher(s: dict) -> None:
    taux = "non disponible" if s["taux_moyen"] is None else f"{s['taux_moyen'] * 100:.1f} %"
    print(f"Réponses LLM : {s['messages']} (dont {s['avec_chiffres']} avec au moins un chiffre vérifié)")
    print(f"Chiffres vérifiés : {s['chiffres']}, non soutenus : {s['non_soutenus']}")
    print(f"Taux moyen de chiffres non soutenus : {taux}")
    print("Distribution du taux par réponse :")
    for _, nom in TRANCHES + ((None, "sans chiffre vérifié"),):
        print(f"  {nom:22s} {s['distribution'].get(nom, 0)}")
    print(f"\n{len(s['top'])} chiffre(s) non soutenu(s) les plus fréquents :")
    for brut, n, origines in s["top"]:
        ids = ", ".join(f"#{i}" for i, _ in origines[:5]) + (" …" if len(origines) > 5 else "")
        message = " ".join((origines[-1][1] or "").split())[:70]
        lisible = "« " + " ".join(brut.split()) + " »"  # espaces fines insécables → espaces
        print(f"  {lisible:16s} ×{n}  messages {ids}  — dernier : « {message} »")


def mode_colonne(conn) -> int:
    if "verification_chiffres" not in {r[1] for r in conn.execute("PRAGMA table_info(message_audit)")}:
        print("Colonne verification_chiffres absente : aucun message du chat depuis la mise à jour "
              "(elle est ajoutée au premier audit). Pour les lignes anciennes : --passe.")
        return 0
    seuil = (datetime.now(timezone.utc) - timedelta(days=JOURS)).isoformat(timespec="seconds")
    lignes = [(r["id"], r["message_utilisateur"], json.loads(r["verification_chiffres"]))
              for r in conn.execute("SELECT id, message_utilisateur, verification_chiffres FROM message_audit "
                                    "WHERE timestamp >= ? AND verification_chiffres IS NOT NULL ORDER BY id",
                                    (seuil,))]
    sans = conn.execute("SELECT COUNT(*) FROM message_audit WHERE timestamp >= ? AND verification_chiffres "
                        "IS NULL AND llm_utilise IN ('gemini', 'groq')", (seuil,)).fetchone()[0]
    print(f"{JOURS} derniers jours, colonne verification_chiffres (lecture seule)\n")
    afficher(statistiques(lignes))
    print(f"\n{sans} réponse(s) LLM sans vérification sur la période (antérieures au branchement, "
          f"ou calcul en échec) : --passe les recalcule.")
    return 0


def _ignore_par_git(chemin: str) -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", chemin], cwd=RACINE).returncode == 0
    except Exception:
        return False


def mode_passe(conn) -> int:
    chemin = os.path.join(DOSSIER_CSV, f"verif_chiffres_{datetime.now():%Y%m%d_%H%M%S}.csv")
    if not _ignore_par_git(chemin):
        print(f"ARRÊT : {DOSSIER_CSV} n'est pas ignoré par git (.gitignore). Aucun fichier écrit.")
        return 1
    lignes, a_etiqueter = [], []
    for r in conn.execute("SELECT id, message_utilisateur, prompt_envoye, reponse_brute FROM message_audit "
                          "WHERE llm_utilise IN ('gemini', 'groq') AND prompt_envoye IS NOT NULL ORDER BY id"):
        refs = references_du_prompt(partie_prompt(r["prompt_envoye"]))
        reponse = r["reponse_brute"] or ""
        lignes.append((r["id"], r["message_utilisateur"], verifier(reponse, refs)))
        _, non_soutenus, _ = classer(reponse, refs)
        a_etiqueter += [(r["id"], n["brut"], extrait(reponse, n["position"], len(n["brut"])), "")
                        for n in non_soutenus]
    print("Recalcul sur toutes les réponses LLM (lecture seule, rien n'est écrit en base)\n")
    afficher(statistiques(lignes))
    os.makedirs(DOSSIER_CSV, exist_ok=True)
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:  # BOM : accents lisibles dans Excel
        w = csv.writer(f, delimiter=";")
        w.writerow(["audit_id", "chiffre", "extrait", "vrai_ou_faux_positif"])
        w.writerows(a_etiqueter)
    print(f"\nCSV d'étiquetage : {chemin} ({len(a_etiqueter)} chiffre(s) à étiqueter)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Contrôle des chiffres du chat (mode avertissement).")
    parser.add_argument("--passe", action="store_true",
                        help="recalculer sur toutes les lignes anciennes et écrire le CSV d'étiquetage")
    a = parser.parse_args()
    conn = _connexion()
    try:
        sys.exit(mode_passe(conn) if a.passe else mode_colonne(conn))
    finally:
        conn.close()
