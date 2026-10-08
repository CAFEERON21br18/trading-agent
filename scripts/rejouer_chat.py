"""
scripts/rejouer_chat.py — Banc de rejeu du chat : mesurer un changement du chat avant de le garder.

MODE D'EMPLOI (sur la tour, depuis la racine du dépôt)
1. Exporter les messages audités (message_audit, lecture seule) :
     .venv\\Scripts\\python.exe scripts\\chat_cas_export.py
   → data/chat_cas/<audit_id>.json (ignoré par git : le portefeuille réel y figure).
2. Ajouter ses questions ; le prompt est construit à blanc (sans LLM ni écriture,
   Alpha Vantage coupé) :
     .venv\\Scripts\\python.exe scripts\\chat_cas_export.py --nouveau "Faut-il alléger NVDA ?"
3. Remplir « attendu » dans 15 cas au moins : doit_contenir, ne_doit_pas_contenir
   (sans casse ni accents), famille (paper, reel, achat_vente, hors_watchlist, theorie,
   suivi), note. Sans doit_contenir ni ne_doit_pas_contenir, un cas reste « non noté ».
4. Ligne de base, sans appel réseau (réponses historiques ; les cas sans réponse,
   manuels ou audit_sans_llm, sont ignorés) :
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --noter
5. Après chaque changement de consigne, régénérer chez Groq puis comparer :
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --rejouer --max 10
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --rejouer --system-fichier essai.txt
     .venv\\Scripts\\python.exe scripts\\rejouer_chat.py --comparer A.json B.json
   Résultats : data/chat_cas/resultats/<horodatage>_<mode>.json. Pour isoler l'effet
   d'une consigne, comparer deux --rejouer (avant, après, même température) : --noter
   mélange l'effet du modèle (Gemini ou Groq) et celui de la consigne.

RÈGLES DU REJEU
- Consigne : celle d'agents/chat/_llm.py (SYSTEM_PROMPT actuel) ; --system-fichier la
  remplace sans modifier _llm.py ; --system-historique reprend celle du cas. Le prompt
  est celui du cas : un changement de la construction du prompt n'est pas mesuré ainsi.
- ask_llm(appelant="banc") : « banc » n'est pas dans GEMINI_RESERVE_POUR, l'appel part chez
  Groq sans toucher aux 20 requêtes Gemini du jour. max_tokens 900 ; --temperature 0,6 par
  défaut (comme le chat) ; --max 10 par défaut, 30 au plus ; 3 s entre deux appels ; arrêt
  propre sur rate_limit_groq ou quota_groq (résultats partiels écrits).
- Jetons estimés avant envoi (longueur ÷ 4, plus le budget de sortie) ; confirmation
  demandée au-delà de 60 000.
- Rien n'est écrit dans message_audit ni chat_history : hors requête auditée, ask_llm ne
  touche pas l'audit, et le script refuse de tourner dans une requête auditée.
  Logs : data/chat_cas/banc.log.
"""

import argparse
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from agents.chat._banc_notation import comparer, famille, noter, resumer
from scripts._banc_fichiers import (DOSSIER_CAS, ecrire_resultats, journaux_detaches, lire_json,
                                    lister_cas, maintenant_iso)

MAX_DEFAUT, MAX_PLAFOND = 10, 30
MAX_TOKENS, PAUSE_S, SEUIL_CONFIRMATION = 900, 3.0, 60_000
ARRETS = ("rate_limit_groq", "quota_groq")


def _ligne(cas: dict, note: dict | None, **extra) -> dict:
    return {"cas": cas["_id"], "famille": famille(cas), "origine": cas.get("origine"), "note": note, **extra}


def noter_historique(dossier: str = DOSSIER_CAS) -> dict:
    """Note les réponses historiques ; aucun appel réseau."""
    tous = lister_cas(dossier)
    avec = [c for c in tous if c.get("reponse_historique")]
    resultats = [_ligne(c, noter(c, c["reponse_historique"]), llm=c.get("llm_historique")) for c in avec]
    return {"mode": "noter", "date": maintenant_iso(), "ignores_sans_reponse": len(tous) - len(avec),
            "resultats": resultats, "resume": resumer(resultats)}


def _consigne(cas: dict, texte_fichier: str | None, historique: bool) -> str:
    if historique:
        return cas.get("system") or ""
    if texte_fichier is not None:
        return texte_fichier
    from agents.chat._llm import SYSTEM_PROMPT
    return SYSTEM_PROMPT


def estimer_jetons(cas_liste: list, consignes: list) -> tuple[int, int]:
    """(entrée ≈ longueur ÷ 4, sortie maximale) ; les modèles gpt-oss reçoivent 1 024 jetons au moins."""
    from utils.llm import GROQ_MIN_TOKENS_RAISONNEUR, _modele_raisonneur, modele_groq
    entree = sum((len(s) + len(c.get("prompt") or "")) // 4 for c, s in zip(cas_liste, consignes))
    par_appel = max(MAX_TOKENS, GROQ_MIN_TOKENS_RAISONNEUR) if _modele_raisonneur(modele_groq()) else MAX_TOKENS
    return entree, len(cas_liste) * par_appel


def _demander(question: str) -> bool:
    return input(f"{question} [o/N] ").strip().lower() in ("o", "oui", "y", "yes")


def rejouer(dossier: str = DOSSIER_CAS, n_max: int = MAX_DEFAUT, temperature: float = 0.6,
            system_fichier: str | None = None, system_historique: bool = False,
            confirmer=_demander, appel=None, pause=time.sleep) -> dict | None:
    """Régénère les réponses chez Groq et les note ; None si l'utilisateur renonce."""
    from utils.audit_trace import _TRACE
    if _TRACE.get() is not None:
        raise RuntimeError("requête auditée en cours : le banc n'appelle pas ask_llm dans ce contexte")
    if appel is None:
        from utils.llm import ask_llm as appel
    texte_fichier = None
    if system_fichier:
        with open(system_fichier, encoding="utf-8") as f:
            texte_fichier = f.read()
    cas_liste = [c for c in lister_cas(dossier) if c.get("prompt")][:max(1, min(n_max, MAX_PLAFOND))]
    consignes = [_consigne(c, texte_fichier, system_historique) for c in cas_liste]
    entree, sortie = estimer_jetons(cas_liste, consignes)
    print(f"{len(cas_liste)} cas à rejouer chez Groq : environ {entree} jetons d'entrée (longueur ÷ 4), "
          f"{sortie} de sortie au plus.")
    if entree + sortie > SEUIL_CONFIRMATION and not confirmer(
            f"Plus de {SEUIL_CONFIRMATION} jetons estimés : continuer ?"):
        print("Abandon : rien n'a été envoyé.")
        return None
    resultats, arret = [], None
    for i, (cas, system) in enumerate(zip(cas_liste, consignes)):
        if i:
            pause(PAUSE_S)
        res = appel(cas["prompt"], system=system, temperature=temperature, max_tokens=MAX_TOKENS,
                    mode="verbose", appelant="banc")
        if res.get("source") and res.get("text"):
            resultats.append(_ligne(cas, noter(cas, res["text"]), source=res["source"], reponse=res["text"]))
            continue
        # Hors réserve Gemini, error vaut « groq_ko:<type>, gemini réservé » : le type est dans tentatives
        erreur = (res.get("tentatives") or [{}])[-1].get("type_erreur") or res.get("error")
        resultats.append(_ligne(cas, None, erreur=erreur))
        if erreur in ARRETS:
            arret = erreur
            break
    return {"mode": "rejouer", "date": maintenant_iso(), "temperature": temperature,
            "consigne": "historique" if system_historique else (system_fichier or "agents/chat/_llm.py"),
            "max_tokens": MAX_TOKENS, "arret": arret, "envoyes": len(resultats), "prevus": len(cas_liste),
            "resultats": resultats, "resume": resumer(resultats)}


def _fmt(v, pct: bool = False) -> str:
    """Inconnu → « — » ; pct : taux en pourcentage (seul le taux de chiffres non soutenus l'est)."""
    return "—" if v is None else (f"{v:.1%}" if pct else str(v))


def _afficher_resume(res: dict) -> None:
    for nom, b in [("GLOBAL", res["resume"]["global"]), *res["resume"]["familles"].items()]:
        print(f"  {nom:15s} {b['cas']:3d} cas · attendu {b['attendu_ok']}/{b['notes']} OK "
              f"({b['non_notes']} non notés) · chiffres non soutenus {_fmt(b['taux_non_soutenus_moyen'], True)} "
              f"· disclaimer manquant {b['echecs_disclaimer']}/{b['disclaimer_requis']} · "
              f"{_fmt(b['nb_lignes_moyen'])} lignes")


def _afficher_comparaison(c: dict) -> None:
    print(f"{c['cas_communs']} cas communs")
    for groupe, metriques in c["ecarts"].items():
        print(f"  {groupe}")
        for m, v in metriques.items():
            pct = m == "taux_non_soutenus_moyen"
            ecart = "" if v["ecart"] is None else (f" ({v['ecart'] * 100:+.1f} pts)" if pct else f" ({v['ecart']:+g})")
            print(f"    {m:24s} {_fmt(v['avant'], pct)} -> {_fmt(v['apres'], pct)}{ecart}")
    print(f"OK -> KO : {', '.join(map(str, c['ok_vers_ko'])) or 'aucun'}")
    print(f"KO -> OK : {', '.join(map(str, c['ko_vers_ok'])) or 'aucun'}")
    print(f"Nouveaux disclaimers manquants : {', '.join(map(str, c['nouveaux_echecs_disclaimer'])) or 'aucun'}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Banc de rejeu du chat (mode d'emploi en tête du fichier).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--noter", action="store_true", help="note les réponses historiques (défaut, sans réseau)")
    g.add_argument("--rejouer", action="store_true", help="régénère chez Groq (appelant « banc »)")
    g.add_argument("--comparer", nargs=2, metavar=("A.json", "B.json"))
    p.add_argument("--max", type=int, default=MAX_DEFAUT, help=f"cas rejoués ({MAX_PLAFOND} au plus)")
    p.add_argument("--temperature", type=float, default=0.6)
    s = p.add_mutually_exclusive_group()
    s.add_argument("--system-fichier", help="consigne à tester, à la place de SYSTEM_PROMPT")
    s.add_argument("--system-historique", action="store_true", help="consigne enregistrée dans le cas")
    a = p.parse_args(argv)
    if a.comparer:
        _afficher_comparaison(comparer(lire_json(a.comparer[0]), lire_json(a.comparer[1])))
        return 0
    if a.rejouer and a.max > MAX_PLAFOND:
        print(f"--max ramené à {MAX_PLAFOND}.")
    with journaux_detaches(DOSSIER_CAS):
        res = (rejouer(n_max=a.max, temperature=a.temperature, system_fichier=a.system_fichier,
                       system_historique=a.system_historique) if a.rejouer else noter_historique())
    if res is None:
        return 1
    chemin = ecrire_resultats(DOSSIER_CAS, res["mode"], res)
    _afficher_resume(res)
    if res.get("arret"):
        print(f"Arrêt propre sur {res['arret']} : {res['envoyes']}/{res['prevus']} cas envoyés.")
    print(f"Résultats : {os.path.relpath(chemin, RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
