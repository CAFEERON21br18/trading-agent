"""
agents/chat/_verif_chiffres.py — Chiffres d'une réponse du chat absents des données envoyées au LLM.

Mode avertissement (TODO §8, justesse) : le résultat est seulement stocké dans
message_audit.verification_chiffres ; la réponse servie à l'utilisateur ne change pas.
Module pur : ni config, ni base, ni réseau.

Un chiffre de la réponse est « soutenu » si une valeur du prompt lui est égale en
valeur absolue, à la précision affichée près (12,3 est soutenu par 12.34) ou à
tolerance_rel près. Les entiers de 0 à 3 sans unité sont comptés à part.
"""

import re

VERSION = 1  # à incrémenter si les règles d'extraction changent (comparaison avec --passe)

_ESP = "[   ]"           # espace, insécable, fine insécable (1 234,56)
_SIGNES = "+\\-−‑–"  # + - − ‑ –
_NOMBRE = re.compile(
    rf"(?P<signe>(?<![\w.,])[{_SIGNES}])?"
    rf"(?P<nb>\d{{1,3}}(?:{_ESP}\d{{3}})+(?:,\d+)?(?!\d)"     # 1 234,56
    r"|\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?|\d{1,3},\d{3}\.\d+"      # 1,234,567 ; 1,234.56
    r"|\d{1,3}(?:\.\d{3}){2,}(?:,\d+)?|\d{1,3}\.\d{3},\d+"      # 1.234.567 ; 1.234,56
    r"|\d+(?:[.,]\d+)?)"                                       # 1234.56 ; 12,3
    r"(?P<k>[kK](?![^\W\d_]))?"                                # 12k
    rf"(?:{_ESP}?(?P<unite>€|%|EUR\b|euros?\b))?")

# Passages qui ne sont jamais des chiffres à vérifier
_EXCLUSIONS = [re.compile(p, f) for p, f in (
    (r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?", 0),  # 2026-10-08
    (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", 0),                                                    # 08/10/2026
    (r"\b\d{1,2}(?::\d{2}){1,2}\b|\b\d{1,2}\s?h(?:\s?\d{2})?\b", 0),                       # 07:30, 15h20, 17 h 16
    (r"\b\d{1,2}(?:er)?\s+(?:janv(?:ier)?|f[ée]vr(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[uû]t"
     r"|sept(?:embre)?|oct(?:obre)?|nov(?:embre)?|d[ée]c(?:embre)?)\b", re.I),               # 8 octobre
    (r"(?:S&P|Nasdaq|Russell|CAC|DAX|FTSE|Nikkei|Stoxx|IBEX)\s?\d+", re.I),               # S&P 500
    (r"\b\d+\.[A-Z]{1,3}\b", 0),                                                             # 2330.TW
    (r"(?m)^[ \t]*(?:[-*>][ \t]*)?\d{1,2}[.)](?=[ \t])", 0),                                 # « 1. », « 2) »
)]
_FRACTION = re.compile(r"(?<![\w/.,])(?P<a>\d{1,2}(?:[.,]\d+)?)\s?/\s?(?P<b>\d{1,3})(?![\w/])")
_MOT_DATE = re.compile(r"\b(?:le|du|au|dès le|depuis le|jusqu'au)\s*$", re.I)
_ORDINAL = re.compile(r"(?:er|re|e|ème|eme|è|nd|nde)\b", re.I)

_MARQUEUR_QUESTION = re.compile(r"^== QUESTION DE L['’]UTILISATEUR ==[ \t]*$", re.M)
_CONSIGNE = re.compile(r"^Ta réponse \(", re.M)
_BLOC_ECHANGES = re.compile(r"^== [ÉE]CHANGES PRÉCÉDENTS.*?(?=^==|\Z)", re.M | re.S)


def _lire(nb: str) -> tuple[float, int]:
    """Texte d'un nombre → (valeur, nombre de décimales affichées)."""
    s = re.sub(_ESP, "", nb)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif s.count(",") > 1 or s.count(".") > 1:
        s = s.replace(",", "").replace(".", "")
    else:
        s = s.replace(",", ".")
    return float(s), len(s.split(".")[1]) if "." in s else 0


def _chevauche(span: tuple, exclus: list) -> bool:
    return any(span[0] < f and d < span[1] for d, f in exclus)


def _dans_identifiant(texte: str, m: re.Match) -> bool:
    """Chiffre d'un identifiant ou d'une version : EMA20, Q3, gpt-oss-120b, SIG-0001, 1.13.0, 3e."""
    debut, fin = m.start("nb"), m.end("nb")
    avant = texte[debut - 1] if debut >= 1 else ""
    avant2 = texte[debut - 2] if debut >= 2 else ""
    if avant.isalpha() or avant == "_":
        return True
    if (avant == "-" and avant2.isalpha()) or (avant == "." and avant2.isalnum()):
        return True
    if m["k"] or m["unite"]:
        return False
    apres = texte[fin:fin + 2]
    return (apres[:1] in (".", ",") and apres[1:].isdigit()) or bool(_ORDINAL.match(texte, fin))


def extraire_nombres(texte: str) -> list[dict]:
    """Nombres du texte : [{valeur, brut, position, unite}], unite ∈ {"€", "%", "/10", None}.
    Ignorés : dates, heures, années seules (2000-2100), numéros de liste, tickers, identifiants."""
    texte = texte or ""
    exclus = [m.span() for rx in _EXCLUSIONS for m in rx.finditer(texte)]
    nombres = []
    for m in _FRACTION.finditer(texte):
        if _chevauche(m.span(), exclus):
            continue
        a, b = m["a"], int(m["b"])
        valeur = float(a.replace(",", "."))
        if b == 10 and not a.startswith("0") and valeur <= 10 \
                and not _MOT_DATE.search(texte[max(0, m.start() - 15):m.start()]):
            nombres.append({"valeur": valeur, "brut": m.group(), "position": m.start(), "unite": "/10"})
            exclus.append(m.span())
        elif a.isdigit() and 1 <= int(a) <= 31 and 1 <= b <= 12:
            exclus.append(m.span())  # date jj/mm ; sinon (13/20) : deux nombres ordinaires
    for m in _NOMBRE.finditer(texte):
        if _chevauche(m.span(), exclus) or _dans_identifiant(texte, m):
            continue
        valeur, _ = _lire(m["nb"])
        if m["k"]:
            valeur *= 1000
        unite = "€" if (m["unite"] or "").lower().startswith(("€", "eur")) else m["unite"]
        if unite is None and not m["k"] and m["nb"].isdigit() and 2000 <= valeur <= 2100:
            continue  # année seule
        if m["signe"] and m["signe"] != "+":
            valeur = -valeur
        nombres.append({"valeur": valeur, "brut": m.group(), "position": m.start(), "unite": unite})
    return sorted(nombres, key=lambda n: n["position"])


def partie_prompt(prompt_envoye: str | None) -> str:
    """Partie [PROMPT] de message_audit.prompt_envoye ([SYSTEM] … [PROMPT] …)."""
    texte = prompt_envoye or ""
    i = texte.find("[PROMPT]\n")
    return texte[i + len("[PROMPT]\n"):] if i >= 0 else texte


def references_du_prompt(prompt: str | None) -> list[float]:
    """Valeurs que le LLM a reçues : tout ce qui précède « == QUESTION DE L'UTILISATEUR == »,
    plus la question (sans la consigne « Ta réponse (4-12 lignes…) »). Le bloc
    « == ÉCHANGES PRÉCÉDENTS » (jusqu'au « == » suivant) n'est jamais une référence."""
    texte = _BLOC_ECHANGES.sub("", prompt or "")
    m = _MARQUEUR_QUESTION.search(texte)
    if m:
        question = texte[m.end():]
        c = _CONSIGNE.search(question)
        texte = texte[:m.start()] + "\n" + (question[:c.start()] if c else question)
    return [n["valeur"] for n in extraire_nombres(texte)]


def _pas(n: dict) -> float:
    """Précision affichée : 0.01 pour « 13,68 € », 1 pour « 7/10 », 1000 pour « 12k »."""
    if n["unite"] == "/10":
        return 1.0
    m = _NOMBRE.search(n["brut"])
    return 10.0 ** -_lire(m["nb"])[1] * (1000 if m["k"] else 1)


def classer(reponse: str, references: list[float], tolerance_rel: float = 0.005) -> tuple[list, list, int]:
    """(soutenus, non soutenus, petits entiers) : nombres de la réponse, au format d'extraire_nombres."""
    refs = [abs(r) for r in references]
    soutenus, non_soutenus, petits = [], [], 0
    for n in extraire_nombres(reponse):
        v = abs(n["valeur"])
        if n["unite"] is None and n["brut"].lstrip(_SIGNES.replace("\\", "")).isdigit() and v <= 3:
            petits += 1
            continue
        demi = _pas(n) / 2 * (1 + 1e-9)
        if any(abs(r - v) <= demi or abs(r - v) <= tolerance_rel * v for r in refs):
            soutenus.append(n)
        else:
            non_soutenus.append(n)
    return soutenus, non_soutenus, petits


def verifier(reponse: str, references: list[float], tolerance_rel: float = 0.005) -> dict:
    """Résumé stocké dans message_audit.verification_chiffres. Taux inconnu (None) sans chiffre."""
    soutenus, non_soutenus, petits = classer(reponse, references, tolerance_rel)
    nb = len(soutenus) + len(non_soutenus)
    return {"version": VERSION, "nb_chiffres": nb, "soutenus": len(soutenus),
            "non_soutenus": [n["brut"] for n in non_soutenus], "petits_entiers": petits,
            "taux_non_soutenus": round(len(non_soutenus) / nb, 4) if nb else None}
