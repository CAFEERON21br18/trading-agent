"""
agents/chat/_banc_resume.py — Agrégation des notes du banc de rejeu du chat : par cas (sur les
passes de --passes N), par famille et au global ; comparaison de deux résultats. Module pur.

Un cas rejoué N fois a N notes ; chaque cas pèse 1 dans les résumés :
- chiffres non soutenus et lignes : moyenne des passes (une passe sans chiffre est exclue du
  taux), écart-type s'il y a au moins deux valeurs, minimum et maximum ;
- attendu, disclaimer, trois blocs : vrai pour le cas si plus de la moitié de ses passes le
  sont (majorité stricte : 2 sur 3, 1 sur 1 ; 1 sur 2 ne suffit pas).
Avec une seule passe (et pour les fichiers d'avant --passes), les chiffres sont ceux d'avant.
"""

from statistics import fmean, stdev

SANS_FAMILLE = "sans_famille"
METRIQUES = ("cas", "notes", "attendu_ok", "taux_non_soutenus_moyen", "echecs_disclaimer",
             "disclaimer_requis", "nb_lignes_moyen", "trois_blocs_requis", "trois_blocs_ok")
_BOOLEENS = ("echec_disclaimer", "disclaimer_requis", "trois_blocs_requis", "trois_blocs_ok")


def _majorite(valeurs: list) -> bool | None:
    v = [x for x in valeurs if x is not None]
    return (2 * sum(1 for x in v if x) > len(v)) if v else None


def _stats(valeurs: list) -> dict:
    v = [x for x in valeurs if x is not None]
    if not v:
        return {"moyenne": None, "ecart_type": None, "min": None, "max": None, "n": 0}
    return {"moyenne": round(fmean(v), 4), "ecart_type": round(stdev(v), 4) if len(v) > 1 else None,
            "min": min(v), "max": max(v), "n": len(v)}


def agreger(resultats: list[dict]) -> dict:
    """{cas: synthèse des passes} ; les lignes sans note (appel en échec) sont ignorées."""
    par_cas: dict[str, dict] = {}
    for r in resultats or []:
        if r.get("note"):
            d = par_cas.setdefault(str(r["cas"]), {"famille": r.get("famille") or SANS_FAMILLE, "notes": []})
            d["notes"].append(r["note"])
    out = {}
    for cas, d in par_cas.items():
        notes = d["notes"]
        attendu = [n.get("attendu_ok") for n in notes]
        out[cas] = {"famille": d["famille"], "passes": len(notes),
                    "taux_non_soutenus": _stats([n.get("taux_non_soutenus") for n in notes]),
                    "nb_lignes": _stats([n.get("nb_lignes") for n in notes]),
                    "attendu_ok": _majorite(attendu),
                    "attendu_ok_passes": sum(1 for a in attendu if a),
                    **{b: _majorite([n.get(b) for n in notes]) for b in _BOOLEENS}}
    return out


def _bloc(synth: list[dict]) -> dict:
    taux = [s["taux_non_soutenus"]["moyenne"] for s in synth if s["taux_non_soutenus"]["moyenne"] is not None]
    notes = [s for s in synth if s["attendu_ok"] is not None]
    lignes = [s["nb_lignes"]["moyenne"] for s in synth if s["nb_lignes"]["moyenne"] is not None]
    return {
        "cas": len(synth),
        "notes": len(notes),
        "non_notes": len(synth) - len(notes),
        "attendu_ok": sum(1 for s in notes if s["attendu_ok"]),
        "taux_non_soutenus_moyen": round(fmean(taux), 4) if taux else None,
        "cas_avec_chiffres": len(taux),
        "echecs_disclaimer": sum(1 for s in synth if s["echec_disclaimer"]),
        "disclaimer_requis": sum(1 for s in synth if s["disclaimer_requis"]),
        "nb_lignes_moyen": round(fmean(lignes), 1) if lignes else None,
        "trois_blocs_requis": sum(1 for s in synth if s["trois_blocs_requis"]),
        "trois_blocs_ok": sum(1 for s in synth if s["trois_blocs_ok"]),
        "passes_max": max((s["passes"] for s in synth), default=0),
    }


def resumer(resultats: list[dict]) -> dict:
    """resultats : [{"cas", "famille", "note", "passe"?}] → {"global", "familles"} (chaque cas pèse 1)."""
    synth = agreger(resultats)
    familles: dict[str, list] = {}
    for s in synth.values():
        familles.setdefault(s["famille"], []).append(s)
    return {"global": _bloc(list(synth.values())),
            "familles": {f: _bloc(v) for f, v in sorted(familles.items())}}


def _ecart(avant: dict | None, apres: dict | None) -> dict:
    avant, apres = avant or {}, apres or {}
    out = {}
    for m in METRIQUES:
        a, b = avant.get(m), apres.get(m)
        out[m] = {"avant": a, "apres": b,
                  "ecart": round(b - a, 4) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None}
    return out


def _cle(c: str):
    return (not c.isdigit(), int(c) if c.isdigit() else 0, c)


def comparer(a: dict, b: dict) -> dict:
    """Écarts par métrique (global, familles), moyennes par cas, cas OK → KO, composition.
    Les résumés sont recalculés depuis les lignes : un ancien fichier compte pour une passe."""
    ca, cb = agreger(a.get("resultats")), agreger(b.get("resultats"))
    ra, rb = resumer(a.get("resultats") or []), resumer(b.get("resultats") or [])
    ecarts = {"global": _ecart(ra["global"], rb["global"])}
    for f in sorted(set(ra["familles"]) | set(rb["familles"])):
        ecarts[f] = _ecart(ra["familles"].get(f), rb["familles"].get(f))
    communs = sorted(set(ca) & set(cb), key=_cle)
    apparies = [c for c in communs if ca[c]["taux_non_soutenus"]["moyenne"] is not None
                and cb[c]["taux_non_soutenus"]["moyenne"] is not None]

    def bascule(cle: str, de, vers) -> list:
        return [c for c in communs if ca[c][cle] is de and cb[c][cle] is vers]
    return {
        "ecarts": ecarts,
        "cas_communs": len(communs),
        "seulement_a": sorted(set(ca) - set(cb), key=_cle),
        "seulement_b": sorted(set(cb) - set(ca), key=_cle),
        "passes": {"a": sorted({s["passes"] for s in ca.values()}), "b": sorted({s["passes"] for s in cb.values()})},
        "par_cas": {c: {"avant": ca[c]["taux_non_soutenus"], "apres": cb[c]["taux_non_soutenus"]} for c in communs},
        "taux_apparie": {"cas": len(apparies),
                         "avant": round(fmean(ca[c]["taux_non_soutenus"]["moyenne"] for c in apparies), 4) if apparies else None,
                         "apres": round(fmean(cb[c]["taux_non_soutenus"]["moyenne"] for c in apparies), 4) if apparies else None},
        "ok_vers_ko": bascule("attendu_ok", True, False),
        "ko_vers_ok": bascule("attendu_ok", False, True),
        "trois_blocs_perdus": bascule("trois_blocs_ok", True, False),
        "nouveaux_echecs_disclaimer": [c for c in communs if not ca[c]["echec_disclaimer"] and cb[c]["echec_disclaimer"]],
    }


def avertissement_comparaison(a: dict, b: dict) -> str | None:
    """--reconstruire ne se compare qu'à un autre --reconstruire du même jour."""
    modes = {a.get("mode"), b.get("mode")}
    if "reconstruire" not in modes:
        return None
    if modes != {"reconstruire"}:
        return ("ATTENTION : --reconstruire comparé à un autre mode (contexte de marché différent). "
                "Résultat non interprétable.")
    if a.get("jour") != b.get("jour"):
        return (f"ATTENTION : --reconstruire de deux jours différents ({a.get('jour')}, {b.get('jour')}) : "
                "contexte de marché différent, résultat non interprétable.")
    return None


def avertissements(a: dict, b: dict, comparaison: dict) -> list[str]:
    """Ce qui rend deux résultats non comparables tels quels (mode, jour, cas, passes, arrêt)."""
    out = [m for m in [avertissement_comparaison(a, b)] if m]
    if comparaison["seulement_a"] or comparaison["seulement_b"]:
        out.append(f"ATTENTION : cas différents (seulement dans A : {comparaison['seulement_a'] or 'aucun'} ; "
                   f"seulement dans B : {comparaison['seulement_b'] or 'aucun'}). Les moyennes globales ne "
                   "portent pas sur les mêmes cas.")
    if comparaison["passes"]["a"] != comparaison["passes"]["b"]:
        out.append(f"ATTENTION : nombres de passes différents (A : {comparaison['passes']['a']}, "
                   f"B : {comparaison['passes']['b']}).")
    for nom, d in (("A", a), ("B", b)):
        if d.get("arret") or (d.get("prevus") is not None and d.get("envoyes") != d.get("prevus")):
            out.append(f"ATTENTION : passage {nom} incomplet ({d.get('envoyes')}/{d.get('prevus')} envois, "
                       f"arrêt : {d.get('arret') or 'aucun'}).")
    if a.get("temperature") != b.get("temperature"):
        out.append(f"ATTENTION : températures différentes ({a.get('temperature')}, {b.get('temperature')}).")
    return out
