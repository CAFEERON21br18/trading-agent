"""
agents/chat/_banc_notation.py — Notation d'une réponse du chat pour le banc de rejeu
(scripts/rejouer_chat.py). Module pur : ni config, ni base, ni réseau, ni log.

noter(cas, texte) mesure :
- taux_non_soutenus : part des chiffres de la réponse absents du prompt
  (_verif_chiffres) ; None sans aucun chiffre, jamais 0 ;
- nb_lignes : lignes non vides ;
- disclaimer : « Pas un conseil financier » présent ; requis si la réponse
  contient BUY, SELL, renforcer, alléger, ou les verbes acheter et vendre
  (achète, achètes, achetez, vends, vend, vendez) ; pas les noms achat ni vente ;
- attendu : doit_contenir et ne_doit_pas_contenir du cas.
Comparaisons insensibles à la casse et aux accents. Un cas sans attendu rempli
est « non noté » (attendu_ok = None), jamais « OK ».
- trois_blocs_ok : format en trois blocs de la consigne v2 (voir trois_blocs_ok).
resumer() agrège par famille ; comparer() met deux résultats côte à côte.
"""

import re
import unicodedata
from statistics import fmean

from agents.chat._verif_chiffres import partie_prompt, references_du_prompt, verifier

FAMILLES = ("paper", "reel", "achat_vente", "hors_watchlist", "theorie", "suivi")
SANS_FAMILLE = "sans_famille"
DISCLAIMER = "pas un conseil financier"
# Sur le texte normalisé (sans accents) ; les noms « achat » et « vente » ne comptent pas
_MOTS_DECISION = re.compile(r"\b(?:buy|sell|renforcer|alleger|acheter|achete|achetes|achetez"
                            r"|vendre|vends|vend|vendez)\b")
METRIQUES = ("cas", "notes", "attendu_ok", "taux_non_soutenus_moyen", "echecs_disclaimer",
             "disclaimer_requis", "nb_lignes_moyen", "trois_blocs_requis", "trois_blocs_ok")
INTENTIONS_TROIS_BLOCS = ("paper_status", "real_status", "advice_buy", "advice_sell")
TITRES_BLOCS = ("les faits", "ma lecture", "ce qui manque")
_INTENTION = re.compile(r"^INTENTION DÉTECTÉE : (\w+)", re.M)
# Titre en début de ligne, mise en forme libre (**, ###, -, 1.), suivi de « : », d'un tiret ou de la fin de ligne
_TITRE = re.compile(r"^[\s>#*_\-\d.)]*(les faits|ma lecture|ce qui manque)\s*(?:\*\*|__)?\s*(?::|-|–|—|$)", re.M)


def normaliser(texte) -> str:
    """Minuscules, sans accents, apostrophe droite, espaces réduits."""
    t = unicodedata.normalize("NFKD", str(texte or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", t.replace("’", "'"))


def _attendu(cas: dict) -> tuple[list, list]:
    a = cas.get("attendu") or {}
    doit = [str(x) for x in a.get("doit_contenir") or [] if str(x).strip()]
    interdits = [str(x) for x in a.get("ne_doit_pas_contenir") or [] if str(x).strip()]
    return doit, interdits


def est_note(cas: dict) -> bool:
    """Un cas est noté si doit_contenir ou ne_doit_pas_contenir est rempli (famille et note ne suffisent pas)."""
    doit, interdits = _attendu(cas)
    return bool(doit or interdits)


def famille(cas: dict) -> str:
    return str((cas.get("attendu") or {}).get("famille") or "").strip() or SANS_FAMILLE


def intention_du_prompt(prompt: str | None) -> str | None:
    """Intention écrite par le chat en tête du prompt (« INTENTION DÉTECTÉE : … »)."""
    m = _INTENTION.search(prompt or "")
    return m.group(1) if m else None


def trois_blocs_requis(prompt: str | None) -> bool:
    """La consigne v2 (règle 6) exige les trois blocs pour paper_status, real_status,
    advice_buy, advice_sell, et general quand des tickers sont cités."""
    intention = intention_du_prompt(prompt)
    return intention in INTENTIONS_TROIS_BLOCS or (
        intention == "general" and "== ANALYSE ACTIFS ==" in (prompt or ""))


def trois_blocs_ok(prompt: str | None, texte: str) -> bool | None:
    """None si l'intention n'exige pas les trois blocs ; sinon True si les titres « Les faits »,
    « Ma lecture » et « Ce qui manque » figurent chacun en début de ligne (mise en forme libre :
    **…**, ###, tiret, numéro), sans casse ni accents.
    APPROXIMATION pour general : « des tickers sont cités » est lu comme « la section
    == ANALYSE ACTIFS == est présente dans le prompt ». Un ticker cité dont l'analyse a échoué
    n'y figure pas : la réponse n'est alors pas exigée en trois blocs."""
    if not trois_blocs_requis(prompt):
        return None
    lignes = "\n".join(normaliser(l) for l in (texte or "").splitlines())
    return set(TITRES_BLOCS) <= {m.group(1) for m in _TITRE.finditer(lignes)}


def noter(cas: dict, texte_reponse: str) -> dict:
    """Note d'une réponse au regard du prompt du cas et de son « attendu »."""
    texte = texte_reponse or ""
    verif = verifier(texte, references_du_prompt(partie_prompt(cas.get("prompt") or "")))
    norme = normaliser(texte)
    requis = bool(_MOTS_DECISION.search(norme))
    present = DISCLAIMER in norme
    doit, interdits = _attendu(cas)
    manques = [f"manque : {d}" for d in doit if normaliser(d) not in norme]
    manques += [f"interdit présent : {x}" for x in interdits if normaliser(x) in norme]
    return {
        "taux_non_soutenus": verif["taux_non_soutenus"],  # None sans chiffre, jamais 0
        "nb_chiffres": verif["nb_chiffres"],
        "non_soutenus": verif["non_soutenus"],
        "nb_lignes": sum(1 for l in texte.splitlines() if l.strip()),
        "disclaimer_present": present,
        "disclaimer_requis": requis,
        "echec_disclaimer": requis and not present,
        "attendu_ok": (not manques) if (doit or interdits) else None,
        "attendu_manques": manques,
        "trois_blocs_requis": trois_blocs_requis(cas.get("prompt")),
        "trois_blocs_ok": trois_blocs_ok(cas.get("prompt"), texte),
    }


def _bloc(notes: list[dict]) -> dict:
    taux = [n["taux_non_soutenus"] for n in notes if n["taux_non_soutenus"] is not None]
    notees = [n for n in notes if n["attendu_ok"] is not None]
    return {
        "cas": len(notes),
        "notes": len(notees),
        "non_notes": len(notes) - len(notees),
        "attendu_ok": sum(1 for n in notees if n["attendu_ok"]),
        "taux_non_soutenus_moyen": round(fmean(taux), 4) if taux else None,
        "cas_avec_chiffres": len(taux),
        "echecs_disclaimer": sum(1 for n in notes if n["echec_disclaimer"]),
        "disclaimer_requis": sum(1 for n in notes if n["disclaimer_requis"]),
        "nb_lignes_moyen": round(fmean(n["nb_lignes"] for n in notes), 1) if notes else None,
        "trois_blocs_requis": sum(1 for n in notes if n.get("trois_blocs_requis")),
        "trois_blocs_ok": sum(1 for n in notes if n.get("trois_blocs_ok")),
    }


def resumer(resultats: list[dict]) -> dict:
    """resultats : [{"cas", "famille", "note"}] ; les lignes sans note (rejeu en échec) sont ignorées."""
    notes = [r for r in resultats if r.get("note")]
    familles: dict[str, list] = {}
    for r in notes:
        familles.setdefault(r.get("famille") or SANS_FAMILLE, []).append(r["note"])
    return {"global": _bloc([r["note"] for r in notes]),
            "familles": {f: _bloc(n) for f, n in sorted(familles.items())}}


def _ecart(avant: dict | None, apres: dict | None) -> dict:
    avant, apres = avant or {}, apres or {}
    out = {}
    for m in METRIQUES:
        a, b = avant.get(m), apres.get(m)
        out[m] = {"avant": a, "apres": b,
                  "ecart": round(b - a, 4) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None}
    return out


def comparer(a: dict, b: dict) -> dict:
    """Écarts par métrique (global et par famille) entre deux fichiers de résultats, cas OK → KO."""
    ra, rb = a.get("resume") or {}, b.get("resume") or {}
    fa, fb = ra.get("familles") or {}, rb.get("familles") or {}
    ecarts = {"global": _ecart(ra.get("global"), rb.get("global"))}
    for f in sorted(set(fa) | set(fb)):
        ecarts[f] = _ecart(fa.get(f), fb.get(f))
    na = {r["cas"]: r["note"] for r in a.get("resultats") or [] if r.get("note")}
    nb = {r["cas"]: r["note"] for r in b.get("resultats") or [] if r.get("note")}
    communs = sorted(set(na) & set(nb), key=str)
    return {
        "ecarts": ecarts,
        "cas_communs": len(communs),
        "ok_vers_ko": [c for c in communs if na[c]["attendu_ok"] is True and nb[c]["attendu_ok"] is False],
        "ko_vers_ok": [c for c in communs if na[c]["attendu_ok"] is False and nb[c]["attendu_ok"] is True],
        "trois_blocs_perdus": [c for c in communs
                               if na[c].get("trois_blocs_ok") is True and nb[c].get("trois_blocs_ok") is False],
        "nouveaux_echecs_disclaimer": [c for c in communs
                                       if not na[c]["echec_disclaimer"] and nb[c]["echec_disclaimer"]],
    }
