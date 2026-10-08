"""
scripts/rejouer_chat.py — Banc de rejeu du chat : mesurer un changement du chat avant de le garder.

MODE D'EMPLOI (sur la tour, depuis la racine du dépôt)
1. Exporter les messages audités (message_audit, lecture seule) :
     .venv\\Scripts\\python.exe scripts\\chat_cas_export.py
   → data/chat_cas/<audit_id>.json (ignoré par git : le portefeuille réel y figure).
2. Ajouter ses questions ; le prompt est construit à blanc (sans LLM ni écriture,
   Alpha Vantage coupé) :
     .venv\\Scripts\\python.exe scripts\\chat_cas_export.py --nouveau "Faut-il alléger NVDA ?"
   Cas « suivi » : remplir à la main "historique_simule", liste dans l'ordre de la
   conversation de {"role": "user" ou "assistant", "texte": …, "il_y_a_min": …}.
3. Remplir « attendu » dans 15 cas au moins : doit_contenir, ne_doit_pas_contenir
   (sans casse ni accents), famille (paper, reel, achat_vente, hors_watchlist, theorie,
   suivi), note. Sans doit_contenir ni ne_doit_pas_contenir, un cas reste « non noté ».
4. Ligne de base, sans appel réseau (réponses historiques ; les cas sans réponse,
   manuels ou audit_sans_llm, sont ignorés) :
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --noter
5. Changement de consigne : deux --rejouer (avant, après, même température), puis comparer :
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --rejouer --max 10
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --rejouer --system-fichier essai.txt
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --comparer A.json B.json
   --noter mélange l'effet du modèle (Gemini ou Groq) et celui de la consigne.
6. Changement de la construction du prompt (ex. historique) : cas manuels seulement,
   prompt refait à blanc avec le code actuel, historique_simule injecté, CHAT_HISTORIQUE
   forcé ; deux --reconstruire le MÊME JOUR (contexte de marché du jour), puis comparer :
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --reconstruire --historique off
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --reconstruire --historique on
   Jamais contre la ligne de base historique ni un --rejouer (--comparer avertit).
Résultats : data/chat_cas/resultats/<horodatage>_<mode>.json.
Métriques : attendu, chiffres non soutenus, disclaimer, lignes, trois_blocs_ok (format
de la consigne v2 : les trois titres présents quand l'intention l'exige).

RÈGLES DU REJEU
- Consigne : celle d'agents/chat/_llm.py (SYSTEM_PROMPT actuel) ; --system-fichier la
  remplace sans modifier _llm.py ; --system-historique (--rejouer) reprend celle du cas.
- ask_llm(appelant="banc") : « banc » n'est pas dans GEMINI_RESERVE_POUR, l'appel part chez
  Groq sans toucher aux 20 requêtes Gemini du jour. max_tokens 900 ; --temperature 0,6 par
  défaut ; --max 10 par défaut, 30 au plus ; 3 s entre deux appels ; arrêt propre sur
  rate_limit_groq ou quota_groq (résultats partiels écrits).
- Jetons estimés avant envoi (longueur ÷ 4, plus le budget de sortie) ; confirmation
  demandée au-delà de 60 000.
- Rien n'est écrit dans message_audit ni chat_history ; le script refuse de tourner dans
  une requête auditée. Logs : data/chat_cas/banc.log.
"""

import argparse
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from agents.chat._banc_notation import comparer
from scripts._banc_fichiers import DOSSIER_CAS, ecrire_resultats, journaux_detaches, lire_json
from scripts._banc_rejeu import (MAX_DEFAUT, MAX_PLAFOND, avertissement_comparaison,  # noqa: F401
                                 estimer_jetons, noter_historique, reconstruire, rejouer)


def _fmt(v, pct: bool = False) -> str:
    """Inconnu → « — » ; pct : taux en pourcentage (seul le taux de chiffres non soutenus l'est)."""
    return "—" if v is None else (f"{v:.1%}" if pct else str(v))


def _afficher_resume(res: dict) -> None:
    for nom, b in [("GLOBAL", res["resume"]["global"]), *res["resume"]["familles"].items()]:
        print(f"  {nom:15s} {b['cas']:3d} cas · attendu {b['attendu_ok']}/{b['notes']} OK "
              f"({b['non_notes']} non notés) · chiffres non soutenus {_fmt(b['taux_non_soutenus_moyen'], True)} "
              f"· disclaimer manquant {b['echecs_disclaimer']}/{b['disclaimer_requis']} · "
              f"trois blocs {b.get('trois_blocs_ok', 0)}/{b.get('trois_blocs_requis', 0)} · "
              f"{_fmt(b['nb_lignes_moyen'])} lignes")


def _afficher_comparaison(c: dict) -> None:
    print(f"{c['cas_communs']} cas communs")
    for groupe, metriques in c["ecarts"].items():
        print(f"  {groupe}")
        for m, v in metriques.items():
            pct = m == "taux_non_soutenus_moyen"
            ecart = "" if v["ecart"] is None else (f" ({v['ecart'] * 100:+.1f} pts)" if pct else f" ({v['ecart']:+g})")
            print(f"    {m:24s} {_fmt(v['avant'], pct)} -> {_fmt(v['apres'], pct)}{ecart}")
    for titre, cle in (("OK -> KO", "ok_vers_ko"), ("KO -> OK", "ko_vers_ok"),
                       ("Trois blocs perdus", "trois_blocs_perdus"),
                       ("Nouveaux disclaimers manquants", "nouveaux_echecs_disclaimer")):
        print(f"{titre} : {', '.join(map(str, c.get(cle) or [])) or 'aucun'}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Banc de rejeu du chat (mode d'emploi en tête du fichier).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--noter", action="store_true", help="note les réponses historiques (défaut, sans réseau)")
    g.add_argument("--rejouer", action="store_true", help="régénère chez Groq (appelant « banc »)")
    g.add_argument("--reconstruire", action="store_true",
                   help="cas manuels : prompt refait à blanc avec le code actuel, puis Groq")
    g.add_argument("--comparer", nargs=2, metavar=("A.json", "B.json"))
    p.add_argument("--historique", choices=("on", "off"), help="avec --reconstruire : CHAT_HISTORIQUE forcé")
    p.add_argument("--max", type=int, default=MAX_DEFAUT, help=f"cas envoyés ({MAX_PLAFOND} au plus)")
    p.add_argument("--temperature", type=float, default=0.6)
    s = p.add_mutually_exclusive_group()
    s.add_argument("--system-fichier", help="consigne à tester, à la place de SYSTEM_PROMPT")
    s.add_argument("--system-historique", action="store_true", help="--rejouer : consigne enregistrée dans le cas")
    a = p.parse_args(argv)
    if a.reconstruire and (a.historique is None or a.system_historique):
        p.error("--reconstruire exige --historique on|off et n'accepte pas --system-historique")
    if a.historique and not a.reconstruire:
        p.error("--historique ne s'emploie qu'avec --reconstruire")
    if a.comparer:
        donnees = [lire_json(f) for f in a.comparer]
        avertissement = avertissement_comparaison(*donnees)
        if avertissement:
            print(avertissement)
        _afficher_comparaison(comparer(*donnees))
        return 0
    if (a.rejouer or a.reconstruire) and a.max > MAX_PLAFOND:
        print(f"--max ramené à {MAX_PLAFOND}.")
    with journaux_detaches(DOSSIER_CAS):
        if a.reconstruire:
            res = reconstruire(DOSSIER_CAS, a.historique == "on", n_max=a.max, temperature=a.temperature,
                               system_fichier=a.system_fichier)
        elif a.rejouer:
            res = rejouer(DOSSIER_CAS, n_max=a.max, temperature=a.temperature, system_fichier=a.system_fichier,
                          system_historique=a.system_historique)
        else:
            res = noter_historique(DOSSIER_CAS)
    if res is None:
        return 1
    chemin = ecrire_resultats(DOSSIER_CAS, res["mode"], res)
    _afficher_resume(res)
    if res.get("arret"):
        print(f"Arrêt propre sur {res['arret']} : {res['envoyes']}/{res['prevus']} cas envoyés.")
    if res.get("rappel"):
        print(res["rappel"])
    print(f"Résultats : {os.path.relpath(chemin, RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
