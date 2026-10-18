"""
scripts/regenerer_graphe.py — Régénère la carte du code (Graphify) et la copie dans le vault Obsidian.

Trois étapes, sans aucun appel LLM :
  1. graphify extract <dépôt> --code-only      extraction AST locale (incrémentale) ;
  2. graphify cluster-only <dépôt> --no-label  communautés laissées en « Community N » ;
  3. scripts/sync_graphify_vault.py            copie dans <vault>/90-Graphify.
Graphify tourne dans un sous-processus (le Python de ce venv) dont l'environnement ne contient
aucune clé d'API : même une option oubliée ne trouverait aucun fournisseur LLM. Le rapport
graphify-out/GRAPH_REPORT.md doit afficher « Token cost: 0 input · 0 output » (vérifié ici).
Sans Graphify (paquet absent du venv), rien n'est fait et rien ne casse (code de sortie 0).
Vault : ALPHASIGNAL_VAULT (environnement ou .env), sinon %USERPROFILE%\\Documents\\AlphaSignalVault.

Usage :
  .venv\\Scripts\\python.exe scripts\\regenerer_graphe.py               # graphe + vault
  .venv\\Scripts\\python.exe scripts\\regenerer_graphe.py --sans-vault  # graphe seulement
  .venv\\Scripts\\python.exe scripts\\regenerer_graphe.py --vault D:\\MonVault
Code de sortie : 0 si tout est fait ou si Graphify manque, 1 si une étape échoue.
Lancé chaque dimanche par scripts/cycle_weekly.py, après le cycle, budget de 10 minutes.
"""

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from utils.logger import get_logger

logger = get_logger(__name__)

SORTIE = os.path.join(RACINE, "graphify-out")
RAPPORT = os.path.join(SORTIE, "GRAPH_REPORT.md")
DELAI_ETAPE_S = 240  # par commande Graphify : 2 × 240 s restent sous le budget de 10 min du weekly
ETAPES = (("extract", ["extract", ".", "--code-only"]),
          ("cluster-only", ["cluster-only", ".", "--no-label"]))
# Variables retirées de l'environnement de Graphify : clés, jetons, adresses et modèles de LLM
_RETIREES = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|BASE_URL|_MODEL$|^OLLAMA)", re.I)
_COUT_NUL = re.compile(r"Token cost:\s*0 input\s*\S\s*0 output")


def graphify_disponible() -> bool:
    return importlib.util.find_spec("graphify") is not None


def environnement_sans_cles(env=None) -> dict:
    """Copie de l'environnement sans aucune variable de clé ni de fournisseur LLM."""
    env = dict(os.environ if env is None else env)
    return {k: v for k, v in env.items() if not _RETIREES.search(k)}


def rapport_sans_llm(chemin: str | None = None) -> bool:
    """Vrai si GRAPH_REPORT.md affiche un coût nul en jetons (0 appel LLM)."""
    try:
        with open(chemin or RAPPORT, encoding="utf-8") as f:
            return bool(_COUT_NUL.search(f.read(4000)))
    except OSError:
        return False


def _graphify(args: list, delai_s: float) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "graphify", *args], cwd=RACINE,
                       env=environnement_sans_cles(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=delai_s)
    lignes = (r.stdout + "\n" + r.stderr).strip().splitlines()
    return r.returncode, " / ".join(lignes[-2:])


def regenerer(vault: str | None = None, avec_vault: bool = True, delai_s: float = DELAI_ETAPE_S) -> dict:
    """Extraction, clustering puis copie dans le vault. Ne lève jamais.
    statut : ok | graphify_absent | echec ; sans_llm : coût nul lu dans GRAPH_REPORT.md."""
    resultat = {"statut": "ok", "etapes": [], "sans_llm": None, "vault": None}
    if not graphify_disponible():
        logger.warning("Graphify absent du venv : carte non régénérée "
                       r"(.venv\Scripts\pip.exe install -r requirements-dev.txt)")
        resultat["statut"] = "graphify_absent"
        return resultat
    try:
        for nom, args in ETAPES:
            t0 = time.time()
            code, fin = _graphify(args, delai_s)
            resultat["etapes"].append({"etape": nom, "code": code, "duree_s": round(time.time() - t0, 1)})
            if code != 0:
                logger.error(f"graphify {nom} : code {code} ({fin})")
                resultat["statut"] = "echec"
                return resultat
        resultat["sans_llm"] = rapport_sans_llm()
        if not resultat["sans_llm"]:
            logger.error("GRAPH_REPORT.md n'affiche pas « Token cost: 0 input · 0 output » : à vérifier")
        if avec_vault:
            from scripts.sync_graphify_vault import sync_vault
            from utils.vault_chemin import dossier_vault
            resultat["vault"] = vault or dossier_vault()
            manquants = sync_vault(SORTIE, resultat["vault"])
            if manquants:
                logger.error(f"Copie dans le vault impossible, fichiers absents : {', '.join(manquants)}")
                resultat["statut"] = "echec"
                return resultat
        logger.info(f"Carte du code régénérée : {resultat['etapes']}, sans LLM : {resultat['sans_llm']}, "
                    f"vault : {resultat['vault'] or 'non copié'}")
    except subprocess.TimeoutExpired as e:
        logger.error(f"graphify : délai de {e.timeout:g} s dépassé, carte non régénérée")
        resultat["statut"] = "echec"
    except Exception as e:
        logger.error(f"Régénération de la carte du code : {e}")
        resultat["statut"] = "echec"
    return resultat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--vault", help="dossier racine du vault (défaut : ALPHASIGNAL_VAULT ou Documents)")
    parser.add_argument("--sans-vault", action="store_true", help="régénère le graphe sans le copier")
    args = parser.parse_args()
    r = regenerer(vault=args.vault, avec_vault=not args.sans_vault)
    print(f"{r['statut']} — étapes {r['etapes']} — sans LLM : {r['sans_llm']} — vault : {r['vault']}")
    return 1 if r["statut"] == "echec" else 0


if __name__ == "__main__":
    sys.exit(main())
