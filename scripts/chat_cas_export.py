"""
scripts/chat_cas_export.py — Cas du banc de rejeu du chat (mode d'emploi : scripts/rejouer_chat.py).

  .venv\\Scripts\\python.exe scripts\\chat_cas_export.py
  .venv\\Scripts\\python.exe scripts\\chat_cas_export.py --nouveau "Faut-il alléger NVDA ?"

Sans option : lit message_audit en lecture seule (mode=ro) et écrit un fichier par
message dans data/chat_cas/<audit_id>.json (ignoré par git : le portefeuille réel y figure) :
- lignes gemini ou groq avec prompt → origine "audit", réponse historique = réponse brute du LLM ;
- lignes rule_based avec prompt (LLM en échec) → origine "audit_sans_llm", réponse vide :
  elles servent au rejeu, pas à --noter.
Un fichier existant n'est jamais réécrit : l'« attendu » rempli à la main est conservé.

--nouveau "question" : prompt construit par le vrai chemin du chat, à blanc
(scripts/_chat_a_blanc.py : sans LLM ni écriture, Alpha Vantage coupé), écrit dans
data/chat_cas/m_<horodatage>.json avec origine "manuel" et une réponse historique vide.
"""

import argparse
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from scripts._banc_fichiers import DOSSIER_CAS, ecrire_exclusif, horodatage, maintenant_iso

LLM_REPONSE = ("gemini", "groq")
NOTES = {26: "essai 08/10", 27: "essai 08/10"}  # essais du contrôle des chiffres (commit 50ad8ee)


def attendu_vide(note: str = "") -> dict:
    return {"doit_contenir": [], "ne_doit_pas_contenir": [], "famille": "", "note": note}


def separer(prompt_envoye: str | None) -> tuple[str, str]:
    """(system, prompt) depuis « [SYSTEM]\\n…\\n\\n[PROMPT]\\n… » (agents/chat/_audit_record.py)."""
    texte = prompt_envoye or ""
    tete, separateur = "[SYSTEM]\n", "\n\n[PROMPT]\n"
    if texte.startswith(tete) and separateur in texte:
        system, prompt = texte[len(tete):].split(separateur, 1)
        return system, prompt
    return "", texte


def lignes_audit(chemin_base: str) -> list[dict]:
    """Lignes de message_audit avec un prompt, base ouverte en lecture seule."""
    conn = sqlite3.connect(f"file:{chemin_base}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, timestamp, message_utilisateur, llm_utilise, prompt_envoye, reponse_brute "
            "FROM message_audit WHERE prompt_envoye IS NOT NULL "
            "AND llm_utilise IN ('gemini', 'groq', 'rule_based') ORDER BY id")]
    finally:
        conn.close()


def cas_depuis_audit(ligne: dict) -> dict:
    system, prompt = separer(ligne["prompt_envoye"])
    avec_llm = ligne["llm_utilise"] in LLM_REPONSE
    return {"audit_id": ligne["id"], "timestamp": ligne["timestamp"],
            "question": ligne["message_utilisateur"], "system": system, "prompt": prompt,
            "reponse_historique": (ligne["reponse_brute"] or "") if avec_llm else "",
            "llm_historique": ligne["llm_utilise"],
            "origine": "audit" if avec_llm else "audit_sans_llm",
            "sources_coupees": [], "attendu": attendu_vide(NOTES.get(ligne["id"], ""))}


def exporter(chemin_base: str, dossier: str = DOSSIER_CAS) -> dict:
    """Un fichier par ligne ; les fichiers existants ne sont pas touchés."""
    compte = {"audit": 0, "audit_sans_llm": 0, "deja_presents": 0}
    for ligne in lignes_audit(chemin_base):
        cas = cas_depuis_audit(ligne)
        if ecrire_exclusif(os.path.join(dossier, f"{ligne['id']}.json"), cas):
            compte[cas["origine"]] += 1
        else:
            compte["deja_presents"] += 1
    return compte


def nouveau(question: str, dossier: str = DOSSIER_CAS) -> tuple[str, dict]:
    """Cas manuel : prompt construit à blanc, aucune réponse."""
    from scripts._chat_a_blanc import construire_cas
    p = construire_cas(question, dossier)
    cas = {"audit_id": None, "timestamp": maintenant_iso(), "question": question,
           "intention": p["intention"], "system": p["system"], "prompt": p["prompt"],
           "reponse_historique": "", "llm_historique": None, "origine": "manuel",
           "sources_coupees": p["sources_coupees"], "attendu": attendu_vide(),
           "historique_simule": []}  # cas « suivi » : à remplir à la main pour --reconstruire
    base = os.path.join(dossier, f"m_{horodatage()}")
    chemin, n = f"{base}.json", 2
    while not ecrire_exclusif(chemin, cas):
        chemin, n = f"{base}_{n}.json", n + 1
    return chemin, cas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Cas du banc de rejeu du chat (data/chat_cas/).")
    parser.add_argument("--nouveau", metavar="QUESTION", help="cas manuel, prompt construit à blanc")
    args = parser.parse_args(argv)
    if args.nouveau:
        chemin, cas = nouveau(args.nouveau)
        coupees = ", ".join(cas["sources_coupees"]) or "aucune (pas d'action citée)"
        print(f"Cas manuel écrit : {os.path.relpath(chemin, RACINE)} — intention {cas['intention']}, "
              f"sources coupées : {coupees}. Remplir « attendu ».")
        return 0
    from utils import database
    c = exporter(database.DB_PATH)
    print(f"Export de message_audit (lecture seule) : {c['audit']} cas avec réponse LLM, "
          f"{c['audit_sans_llm']} sans réponse LLM (rejeu seulement), "
          f"{c['deja_presents']} déjà présents (non réécrits).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
