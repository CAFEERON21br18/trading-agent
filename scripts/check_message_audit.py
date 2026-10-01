"""
scripts/check_message_audit.py — Vérification manuelle de l'audit du chat (Phase 4).

Usage : .venv\\Scripts\\python.exe -X utf8 scripts\\check_message_audit.py [N] [--complet]

1. Auto-test du masquage (utils/secret_mask) avec les vraies valeurs de .env :
   aucune valeur n'est affichée, seulement OK / ÉCHEC par variable.
2. Affiche les N derniers enregistrements de message_audit (défaut 1).
3. Compare l'empreinte des clés chargées par le dashboard (enregistrée dans
   chaine_de_fallback) avec celle de .env : un écart = dashboard qui tourne
   avec une clé périmée → redémarrer la tâche \\AlphaSignal\\dashboard.
Lecture seule : n'écrit rien en base.
"""

import json
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from dotenv import dotenv_values

import config  # charge .env (load_dotenv) avant le masquage
from utils.database import DB_PATH
from utils.secret_mask import masquer_secrets, empreinte_secret, _valeurs_secretes

TRONQUE = 600


def test_masquage() -> bool:
    """Chaque secret de .env doit disparaître de textes typiques (URL, en-tête, erreur)."""
    ok = True
    for nom, val in _valeurs_secretes():
        gabarits = [f"https://api.example.com/v2?q=x&apiKey={val}&page=1",
                    f"Authorization: Bearer {val}", f"Erreur 401 : clé {val} refusée",
                    json.dumps({"cle": val})]
        fuite = [g for g in gabarits if val in masquer_secrets(g)]
        print(f"  {'✅' if not fuite else '❌'} {nom:24s} {'masqué' if not fuite else 'FUITE'}")
        ok &= not fuite
    synthetiques = ["gsk_" + "A1b2" * 10, "AIza" + "x" * 35, "Bearer abcdefgh12345678"]
    for s in synthetiques:
        masque = masquer_secrets(s)
        fuite = s in masque
        print(f"  {'✅' if not fuite else '❌'} motif {s[:6]}…{'':13s} → {masque}")
        ok &= not fuite
    return ok


def _afficher(champ: str, valeur, complet: bool) -> None:
    if valeur is None:
        print(f"  {champ:28s}: NULL")
        return
    texte = str(valeur)
    if champ in ("contexte_injecte", "chaine_de_fallback", "actions_declenchees",
                 "decisions_trading_generees", "origine_client"):
        try:
            texte = json.dumps(json.loads(texte), ensure_ascii=False, indent=2)
        except Exception:
            pass
    if not complet and len(texte) > TRONQUE:
        texte = texte[:TRONQUE] + f"\n  … ({len(texte)} caractères, --complet pour tout voir)"
    print(f"  {champ:28s}: {texte}")


def comparer_cles(chaine_json: str | None) -> None:
    """Empreintes du dashboard (enregistrement) vs .env sur disque."""
    try:
        conf = next(e for e in json.loads(chaine_json or "[]") if e.get("etape") == "configuration")
    except (StopIteration, ValueError):
        print("  ⚠️  Pas d'étape 'configuration' dans chaine_de_fallback.")
        return
    env = dotenv_values(os.path.join(RACINE, ".env"))
    for fournisseur, var in (("gemini", "GEMINI_API_KEY"), ("groq", "GROQ_API_KEY")):
        dash, disque = conf.get(f"{fournisseur}_cle"), empreinte_secret(env.get(var))
        etat = "✅ identique" if dash == disque else "❌ DIFFÉRENTE — redémarrer le dashboard"
        print(f"  {var:16s} dashboard={dash}  .env={disque}  {etat}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n, complet = (int(args[0]) if args else 1), "--complet" in sys.argv

    print("1. Auto-test du masquage")
    masquage_ok = test_masquage()

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        lignes = conn.execute("SELECT * FROM message_audit ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"\n❌ message_audit illisible : {e} (aucun message audité depuis l'installation ?)")
        return 1
    finally:
        conn.close()

    print(f"\n2. {len(lignes)} dernier(s) enregistrement(s) de message_audit")
    for ligne in lignes:
        print(f"\n── #{ligne['id']} ─────────────────────────────────────────")
        for champ in ligne.keys():
            if champ != "id":
                _afficher(champ, ligne[champ], complet)
    if lignes:
        print("\n3. Clés chargées par le dashboard vs .env (dernier enregistrement)")
        comparer_cles(lignes[0]["chaine_de_fallback"])
    return 0 if masquage_ok else 2


if __name__ == "__main__":
    sys.exit(main())
