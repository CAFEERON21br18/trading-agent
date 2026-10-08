"""
scripts/_banc_rejeu.py — Logique du banc de rejeu du chat (ligne de commande et mode
d'emploi : scripts/rejouer_chat.py).

- noter_historique : note les réponses historiques, sans réseau ;
- rejouer : régénère chez Groq à partir des prompts stockés ;
- reconstruire : cas manuels seulement, prompt refait à blanc avec le code ACTUEL
  (historique_simule injecté, CHAT_HISTORIQUE forcé), puis Groq. Le contexte de marché
  est celui du jour : ne comparer que deux --reconstruire lancés le même jour.
Hors requête auditée, ask_llm n'écrit ni dans message_audit ni dans chat_history.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.chat._banc_notation import famille, noter, resumer
from scripts._banc_fichiers import lister_cas, maintenant_iso

MAX_DEFAUT, MAX_PLAFOND = 10, 30
MAX_TOKENS, PAUSE_S, SEUIL_CONFIRMATION = 900, 3.0, 60_000
ARRETS = ("rate_limit_groq", "quota_groq")
RAPPEL_RECONSTRUIRE = ("Rappel : --reconstruire refait le contexte avec les données de marché du jour. "
                       "Ne comparer que deux --reconstruire lancés le même jour, jamais avec la ligne "
                       "de base historique (--noter) ni avec un --rejouer.")


def _ligne(cas: dict, note: dict | None, **extra) -> dict:
    return {"cas": cas["_id"], "famille": famille(cas), "origine": cas.get("origine"), "note": note, **extra}


def _jour() -> str:
    """Jour de Lisbonne (config.TIMEZONE) : deux --reconstruire ne se comparent que le même jour."""
    import config
    return datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()


def noter_historique(dossier: str) -> dict:
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


def _lire_consigne(system_fichier: str | None) -> str | None:
    if not system_fichier:
        return None
    with open(system_fichier, encoding="utf-8") as f:
        return f.read()


def estimer_jetons(cas_liste: list, consignes: list) -> tuple[int, int]:
    """(entrée ≈ longueur ÷ 4, sortie maximale) ; les modèles gpt-oss reçoivent 1 024 jetons au moins."""
    from utils.llm import GROQ_MIN_TOKENS_RAISONNEUR, _modele_raisonneur, modele_groq
    entree = sum((len(s) + len(c.get("prompt") or "")) // 4 for c, s in zip(cas_liste, consignes))
    par_appel = max(MAX_TOKENS, GROQ_MIN_TOKENS_RAISONNEUR) if _modele_raisonneur(modele_groq()) else MAX_TOKENS
    return entree, len(cas_liste) * par_appel


def _demander(question: str) -> bool:
    return input(f"{question} [o/N] ").strip().lower() in ("o", "oui", "y", "yes")


def _preparer(appel):
    from utils.audit_trace import _TRACE
    if _TRACE.get() is not None:
        raise RuntimeError("requête auditée en cours : le banc n'appelle pas ask_llm dans ce contexte")
    if appel is None:
        from utils.llm import ask_llm as appel
    return appel


def _envoyer(entrees: list, temperature: float, confirmer, appel, pause) -> tuple | None:
    """entrees : [(cas, prompt, consigne, infos)] → (resultats, arret) ; None si l'utilisateur renonce."""
    entree, sortie = estimer_jetons([{"prompt": p} for _, p, _, _ in entrees], [s for _, _, s, _ in entrees])
    print(f"{len(entrees)} cas à envoyer chez Groq : environ {entree} jetons d'entrée (longueur ÷ 4), "
          f"{sortie} de sortie au plus.")
    if entree + sortie > SEUIL_CONFIRMATION and not confirmer(
            f"Plus de {SEUIL_CONFIRMATION} jetons estimés : continuer ?"):
        print("Abandon : rien n'a été envoyé.")
        return None
    resultats, arret = [], None
    for i, (cas, prompt, consigne, infos) in enumerate(entrees):
        if i:
            pause(PAUSE_S)
        res = appel(prompt, system=consigne, temperature=temperature, max_tokens=MAX_TOKENS,
                    mode="verbose", appelant="banc")
        if res.get("source") and res.get("text"):
            note = noter({**cas, "prompt": prompt}, res["text"])  # références : le prompt envoyé
            resultats.append(_ligne(cas, note, source=res["source"], reponse=res["text"], **infos))
            continue
        # Hors réserve Gemini, error vaut « groq_ko:<type>, gemini réservé » : le type est dans tentatives
        erreur = (res.get("tentatives") or [{}])[-1].get("type_erreur") or res.get("error")
        resultats.append(_ligne(cas, None, erreur=erreur, **infos))
        if erreur in ARRETS:
            arret = erreur
            break
    return resultats, arret


def _plafond(n_max: int) -> int:
    return max(1, min(n_max, MAX_PLAFOND))


def rejouer(dossier: str, n_max: int = MAX_DEFAUT, temperature: float = 0.6,
            system_fichier: str | None = None, system_historique: bool = False,
            confirmer=_demander, appel=None, pause=time.sleep) -> dict | None:
    """Régénère chez Groq à partir des prompts stockés ; None si l'utilisateur renonce."""
    appel = _preparer(appel)
    texte = _lire_consigne(system_fichier)
    cas_liste = [c for c in lister_cas(dossier) if c.get("prompt")][:_plafond(n_max)]
    envoi = _envoyer([(c, c["prompt"], _consigne(c, texte, system_historique), {}) for c in cas_liste],
                     temperature, confirmer, appel, pause)
    if envoi is None:
        return None
    resultats, arret = envoi
    return {"mode": "rejouer", "date": maintenant_iso(), "jour": _jour(), "temperature": temperature,
            "consigne": "historique" if system_historique else (system_fichier or "agents/chat/_llm.py"),
            "max_tokens": MAX_TOKENS, "arret": arret, "envoyes": len(resultats), "prevus": len(cas_liste),
            "resultats": resultats, "resume": resumer(resultats)}


def reconstruire(dossier: str, historique: bool, n_max: int = MAX_DEFAUT, temperature: float = 0.6,
                 system_fichier: str | None = None, confirmer=_demander, appel=None,
                 pause=time.sleep, construire=None) -> dict | None:
    """Cas manuels : prompt refait à blanc (code actuel), historique_simule à la place de
    chat_history, CHAT_HISTORIQUE forcé à historique ; puis Groq. None si l'utilisateur renonce."""
    appel = _preparer(appel)
    if construire is None:
        from scripts._chat_a_blanc import construire_cas as construire
    texte = _lire_consigne(system_fichier)
    cas_liste = [c for c in lister_cas(dossier) if c.get("origine") == "manuel" and c.get("question")]
    entrees = []
    for c in cas_liste[:_plafond(n_max)]:
        p = construire(c["question"], dossier, historique_simule=c.get("historique_simule") or [],
                       chat_historique=historique)
        infos = {"intention": p["intention"], "sources_coupees": p["sources_coupees"],
                 "tickers_herites": p.get("tickers_herites"), "messages_historique": p.get("messages_historique"),
                 "prompt": p["prompt"]}
        entrees.append((c, p["prompt"], texte if texte is not None else p["system"], infos))
    print(RAPPEL_RECONSTRUIRE)
    envoi = _envoyer(entrees, temperature, confirmer, appel, pause)
    if envoi is None:
        return None
    resultats, arret = envoi
    return {"mode": "reconstruire", "historique": "on" if historique else "off", "date": maintenant_iso(),
            "jour": _jour(), "temperature": temperature, "consigne": system_fichier or "agents/chat/_llm.py",
            "max_tokens": MAX_TOKENS, "arret": arret, "envoyes": len(resultats), "prevus": len(entrees),
            "rappel": RAPPEL_RECONSTRUIRE, "resultats": resultats, "resume": resumer(resultats)}


def avertissement_comparaison(a: dict, b: dict) -> str | None:
    """--reconstruire ne se compare qu'à un autre --reconstruire du même jour."""
    modes = {a.get("mode"), b.get("mode")}
    if "reconstruire" not in modes:
        return None
    if modes != {"reconstruire"}:
        return "ATTENTION : --reconstruire comparé à un autre mode (contexte de marché différent). " \
               "Résultat non interprétable."
    if a.get("jour") != b.get("jour"):
        return f"ATTENTION : --reconstruire de deux jours différents ({a.get('jour')}, {b.get('jour')}) : " \
               "contexte de marché différent, résultat non interprétable."
    return None
