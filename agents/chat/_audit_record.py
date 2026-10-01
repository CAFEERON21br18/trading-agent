"""
agents/chat/_audit_record.py — Construction d'un enregistrement message_audit.

Isolé de _audit.py (limite de 200 lignes). Tous les champs texte et JSON
passent par utils.secret_mask.masquer_secrets avant stockage.

Règle passe_par_* (Phase 4) : calculée sur les écritures persistantes
(hors chat_history, message_audit et caches de marché).
  - NULL : aucune écriture persistante (message sans action)
  - 1    : toutes ces écritures ont eu lieu dans le Decision Engine
           (resp. le Budget Manager)
  - 0    : au moins une écriture hors DE (resp. hors BM) → contournement
"""

import json

import config
from utils.audit_trace import TABLES_CACHE
from utils.llm import MODEL_GEMINI, cle_groq, modele_groq
from utils.secret_mask import masquer_secrets, empreinte_secret

_SOURCES_LLM = ("gemini", "groq")
# Bornes du contexte stocké (le texte réellement injecté est dans prompt_envoye).
# 20 = max positions simultanées : les listes de positions ne sont jamais coupées ;
# real_advice (1 248 conseils, ~500 Ko au 01/10) l'est, avec son total.
_MAX_ELEMENTS = 20
_MAX_CHAINE = 4000


def _compacter(obj):
    """Listes > 20 éléments : 20 premiers + total ; chaînes > 4000 car. : coupées."""
    if isinstance(obj, dict):
        return {k: _compacter(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        items = [_compacter(v) for v in obj[:_MAX_ELEMENTS]]
        if len(obj) > _MAX_ELEMENTS:
            items.append({"_tronque": f"{len(obj) - _MAX_ELEMENTS} élément(s) non stocké(s) "
                                      f"sur {len(obj)}"})
        return items
    if isinstance(obj, str) and len(obj) > _MAX_CHAINE:
        return obj[:_MAX_CHAINE] + f"… [tronqué, {len(obj)} caractères]"
    return obj


def _json(obj) -> str | None:
    if obj is None:
        return None
    return masquer_secrets(json.dumps(obj, ensure_ascii=False, default=str))


def _config_llm() -> dict:
    """Clés effectivement chargées par CE processus (empreintes, jamais les valeurs)."""
    return {"etape": "configuration",
            "gemini_modele": MODEL_GEMINI,
            "gemini_cle": empreinte_secret(getattr(config, "GEMINI_API_KEY", None)),
            "groq_modele": modele_groq(),
            "groq_cle": empreinte_secret(cle_groq())}


def _message_et_contexte(type_message, args, kwargs, trace):
    if type_message == "plan":
        session = kwargs.get("session_id", args[0] if args else None)
        message = kwargs.get("message", args[1] if len(args) > 1 else None)
        contexte = trace.contexte or {"session_id": session, "etape": "demarrage"}
        return message, contexte
    return kwargs.get("question", args[0] if args else None), trace.contexte


def _source(type_message: str, client: dict) -> str:
    if client.get("referer_path") != "/chat":
        return "autre"
    return "pwa_plan" if type_message == "plan" else "pwa"


def _champs_llm(type_message, trace, resultat) -> dict:
    """llm_utilise, chaîne de fallback, prompt, réponse brute, erreur LLM."""
    resultat = resultat if isinstance(resultat, dict) else {}
    chaine = [_config_llm()]
    if type_message != "chat":
        chaine.append({"fournisseur": "rule_based", "ok": True,
                       "raison": "création de plan : machine à états, sans LLM"})
        return {"llm": "rule_based", "chaine": chaine, "prompt": None,
                "brute": resultat.get("reponse"), "erreur": None}

    source = resultat.get("source") or ""
    appel = trace.appel_principal
    prompt = None
    if appel:
        res = appel.get("resultat") or {}
        chaine += res.get("tentatives") or []
        prompt = f"[SYSTEM]\n{appel.get('system') or ''}\n\n[PROMPT]\n{appel.get('prompt') or ''}"
    elif source == "llm_indispo:clé_manquante":
        chaine.append({"fournisseur": "gemini", "ok": False, "type_erreur": "clé_manquante",
                       "note": "Groq non tenté : clé Gemini absente (agents/chat/_llm.py)"})

    llm = source if source in _SOURCES_LLM else "rule_based"
    if llm == "rule_based":
        chaine.append({"fournisseur": "rule_based", "ok": True, "raison": source or None})
        brute = resultat.get("reponse")       # bandeau + template réellement servis
    else:
        brute = (appel.get("resultat") or {}).get("text") if appel else resultat.get("reponse")
    erreur = source if source.startswith("llm_indispo") else None
    return {"llm": llm, "chaine": chaine, "prompt": prompt, "brute": brute, "erreur": erreur}


def _actions(trace) -> tuple[dict, int | None, int | None]:
    """actions_declenchees + passe_par_decision_engine + passe_par_budget_manager."""
    ecritures = [
        {"type": t, "cible": c, "operation": op, "nb": n,
         "categorie": "cache" if (t == "sqlite" and c in TABLES_CACHE) else "persistante",
         "via_decision_engine": de, "via_budget_manager": bm}
        for (t, c, op, de, bm), n in trace.ecritures.items()
    ]
    persistantes = [e for e in ecritures if e["categorie"] == "persistante"]
    if persistantes:
        par_de = int(all(e["via_decision_engine"] for e in persistantes))
        par_bm = int(all(e["via_budget_manager"] for e in persistantes))
    else:
        par_de = par_bm = None
    actions = {
        "ecritures": ecritures,
        "decider_lances": [i["cible"] for i in trace.invocations if i["zone"] == "decision_engine"],
        "budget_manager_lance": any(i["zone"] == "budget_manager" for i in trace.invocations),
        "appels_llm": {"total": len(trace.appels_llm), "detail": trace.appels_llm},
    }
    return actions, par_de, par_bm


def construire_enregistrement(type_message, args, kwargs, trace, resultat, exc,
                              horodatage: str, latence_ms: int, client: dict) -> dict:
    """Assemble l'enregistrement message_audit (tous champs texte masqués)."""
    message, contexte = _message_et_contexte(type_message, args, kwargs, trace)
    llm = _champs_llm(type_message, trace, resultat)
    actions, par_de, par_bm = _actions(trace)

    if exc is not None:
        erreur = f"{type(exc).__name__}: {exc}"
    elif type_message == "plan" and isinstance(resultat, dict) and resultat.get("etat") == "erreur":
        erreur = resultat.get("reponse")
    else:
        erreur = llm["erreur"]

    return {
        "timestamp":                  horodatage,
        "source":                     _source(type_message, client),
        "message_utilisateur":        masquer_secrets(message),
        "contexte_injecte":           _json(_compacter(contexte)),
        "llm_utilise":                llm["llm"],
        "chaine_de_fallback":         _json(llm["chaine"]),
        "prompt_envoye":              masquer_secrets(llm["prompt"]),
        "reponse_brute":              masquer_secrets(llm["brute"]),
        "actions_declenchees":        _json(actions),
        "decisions_trading_generees": _json(trace.invocations),
        "passe_par_decision_engine":  par_de,
        "passe_par_budget_manager":   par_bm,
        "latence_ms":                 latence_ms,
        "erreur":                     masquer_secrets(erreur),
        "origine_client":             _json(client),
    }
