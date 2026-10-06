"""
dashboard/api/watchlist_io.py — data/watchlist.json lu et écrit par le dashboard (Phase 4, P14).

L'ordre du fichier compte : le tactical n'analyse que les 8 premiers actifs hors positions
ouvertes, et l'ordre entre dans l'empreinte des paramètres du registre (R3). TODO §16 : Flask
triait les clés en JSON, et la page Settings renvoyait cet objet trié à chaque clic. Ici :
- la lecture est renvoyée sans tri ;
- un changement limité aux booléens « actif » ne modifie que ces booléens, sur leur ligne
  (mise en forme du fichier conservée) ;
- tout autre changement est réécrit dans l'ordre du fichier existant (clés nouvelles à la fin).
Écriture atomique (os.replace) : un cycle ne lit jamais un fichier à moitié écrit.
"""

import json
import os
import re
import time

from flask import Response

import config

CHEMIN = config.WATCHLIST_FILE


def reponse_sans_tri(data) -> Response:
    """JSON dans l'ordre des clés (jsonify les trie : DefaultJSONProvider.sort_keys)."""
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/json")


def _lire_texte(chemin: str) -> str:
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def _ecrire_texte(chemin: str, texte: str) -> None:
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(texte)
    for essai in range(5):  # Windows : refus possible si un cycle lit le fichier à cet instant
        try:
            os.replace(tmp, chemin)
            return
        except PermissionError:
            if essai == 4:
                raise
            time.sleep(0.1)


def _dans_l_ordre(ancien, nouveau):
    """Contenu de `nouveau`, dans l'ordre des clés de `ancien` ; clés nouvelles à la fin."""
    if not (isinstance(ancien, dict) and isinstance(nouveau, dict)):
        return nouveau
    out = {k: _dans_l_ordre(ancien[k], nouveau[k]) for k in ancien if k in nouveau}
    out.update((k, v) for k, v in nouveau.items() if k not in out)
    return out


def _changements_actif(ancien: dict, cible: dict) -> list | None:
    """[(catégorie, ticker, actif)] si seuls des booléens « actif » diffèrent, sinon None."""
    if list(ancien) != list(cible):
        return None
    changements = []
    for cat, a in ancien.items():
        c = cible[cat]
        if not (isinstance(a, dict) and isinstance(c, dict)) or list(a) != list(c):
            if a != c:
                return None
            continue
        for t, ia in a.items():
            ic = c[t]
            if not (isinstance(ia, dict) and isinstance(ic, dict)):
                if ia != ic:
                    return None
                continue
            if {k: v for k, v in ia.items() if k != "actif"} != {k: v for k, v in ic.items() if k != "actif"}:
                return None
            if ia.get("actif", True) != ic.get("actif", True):
                changements.append((cat, t, bool(ic.get("actif", True))))
    return changements


def _basculer_texte(texte: str, cat: str, ticker: str, actif: bool) -> str | None:
    """Remplace le booléen « actif » de l'actif dans le texte ; None si la forme n'est pas reconnue."""
    m = re.search(r'"%s"\s*:\s*\{' % re.escape(cat), texte)
    if not m:
        return None
    mt = re.compile(r'"%s"\s*:\s*\{[^{}]*?"actif"\s*:\s*(true|false)' % re.escape(ticker)).search(texte, m.end())
    if not mt:
        return None
    return texte[:mt.start(1)] + ("true" if actif else "false") + texte[mt.end(1):]


def ecrire_watchlist(chemin: str, nouveau: dict) -> None:
    """Écrit `nouveau` sans jamais réordonner le fichier existant."""
    texte = _lire_texte(chemin)
    ancien = json.loads(texte)
    cible = _dans_l_ordre(ancien, nouveau)
    changements = _changements_actif(ancien, cible)
    if changements is not None:
        t = texte
        for cat, ticker, actif in changements:
            t = _basculer_texte(t, cat, ticker, actif) if t is not None else None
        # Contrôle : le texte modifié relu donne exactement la cible, ordre compris
        if t is not None and json.dumps(json.loads(t), ensure_ascii=False) == json.dumps(cible, ensure_ascii=False):
            if t != texte:
                _ecrire_texte(chemin, t)
            return
    nl = "\r\n" if "\r\n" in texte else "\n"
    _ecrire_texte(chemin, json.dumps(cible, indent=2, ensure_ascii=False).replace("\n", nl) + nl)


def basculer_actif(chemin: str, cat: str, ticker: str, actif: bool) -> str | None:
    """Change seulement « actif » de cet actif. Retourne un message d'erreur, ou None."""
    ancien = json.loads(_lire_texte(chemin))
    if not isinstance(ancien.get(cat), dict) or not isinstance(ancien[cat].get(ticker), dict):
        return f"actif inconnu : {cat}/{ticker}"
    nouveau = json.loads(json.dumps(ancien))
    nouveau[cat][ticker]["actif"] = bool(actif)
    ecrire_watchlist(chemin, nouveau)
    return None
