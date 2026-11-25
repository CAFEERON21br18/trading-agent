"""
rejeu/lancement.py — Un lancement complet du rejeu : les six configurations et leurs références.

1. barres du cache (rejeu/donnees.py) ; titres inutilisables écartés ;
2. analyse technique de chaque titre et de chaque jour, une fois, par les fonctions de l'agent ;
3. simulation des six configurations (3 capitaux × 2 profils de frais), chacune dans son
   processus et sur sa base jetable ; références « acheter et garder » ;
4. écriture dans data/rejeu/ledger_rejeu.db par ledger/ecriture.py (le grand livre du lancement
   précédent est archivé, jamais effacé) ; résumé dans data/rejeu/lancement.json ; rapport.
Rien n'est écrit hors de data/rejeu/ et de reports/rejeu/.
"""

import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import ledger
from rejeu import analyse, donnees, enveloppe, grand_livre, moteur, reference
from rejeu import parametres as P

COMMIT_DU_CRITERE = "d195259"  # commit de la section 10 du registre
CODE_DE_L_AGENT = ("agents", "utils", "alerts", "config.py")
_partage = {}


def _preparer(barres: dict, analyses: dict) -> None:
    analyse._preparer_processus()
    _partage.update(barres=barres, analyses=analyses)


def _simuler(argument: tuple):
    capital, profil, chemin_base = argument
    return moteur.simuler(capital, profil, _partage["barres"], _partage["analyses"], chemin_base)


def _git(*arguments: str) -> str | None:
    try:
        sortie = subprocess.run(["git", *arguments], cwd=P.RACINE, capture_output=True, text=True, timeout=30)
        return sortie.stdout.strip() if sortie.returncode == 0 else None
    except Exception:
        return None


def code_agent_inchange() -> bool | None:
    """Vrai si le code de l'agent est celui du commit du critère (None : git indisponible)."""
    if _git("rev-parse", "HEAD") is None:
        return None
    sortie = subprocess.run(["git", "diff", "--quiet", COMMIT_DU_CRITERE, "--", *CODE_DE_L_AGENT], cwd=P.RACINE)
    return sortie.returncode == 0


def lancer(dossier: str | None = None, dossier_rapport: str | None = None, processus: int = 1,
           barres: dict | None = None, analyses: dict | None = None, ecrire_rapport: bool = True) -> dict:
    """Lance les six configurations. `barres` et `analyses` : fournis par les tests, sinon lus et calculés."""
    dossier = dossier or P.DOSSIER
    debut, durees = time.perf_counter(), {}
    lance_le = datetime.now(timezone.utc)
    # d'abord : les sorties du lancement précédent vont dans archives/ (rien n'est effacé)
    grand_livre.archiver(lance_le.strftime("%Y%m%d-%H%M%S"), dossier, dossier_rapport)
    tickers = list(donnees.univers())
    controles = {}
    if barres is None:
        barres, controles = donnees.charger(tickers, dossier)
        if not barres:
            raise RuntimeError("aucune barre en cache : lancer d'abord scripts/rejeu_donnees.py")
    if analyses is None:
        analyses = analyse.analyser_univers(barres, processus)
    durees["analyses"] = round(time.perf_counter() - debut, 1)

    configs = [(c, p) for c in P.CAPITAUX for p in P.PROFILS]
    taches = [(c, p, os.path.join(dossier, f"agent_{c}_{p}.db")) for c, p in configs]
    t = time.perf_counter()
    if processus <= 1:
        _preparer(barres, analyses)
        strategies = [_simuler(tache) for tache in taches]
    else:
        with ProcessPoolExecutor(max_workers=min(processus, len(taches)), initializer=_preparer,
                                 initargs=(barres, analyses)) as executeur:
            strategies = list(executeur.map(_simuler, taches))
    references = [f(c, p, barres) for c, p in configs for f in (reference.annuelle, reference.periode)]
    durees["simulations"] = round(time.perf_counter() - t, 1)

    t = time.perf_counter()
    os.makedirs(dossier, exist_ok=True)
    conn = ledger.ouvrir(grand_livre.chemin(dossier))
    try:
        for resultat in strategies + references:
            grand_livre.ecrire(conn, resultat)
        conn.commit()
    finally:
        conn.close()
    durees["ecriture"] = round(time.perf_counter() - t, 1)
    durees["total"] = round(time.perf_counter() - debut, 1)

    par_capital = {c: [tuple((o.ref, o.quand, o.quantite, o.prix) for o in s.ordres)
                       for s in strategies if s.capital == c] for c in P.CAPITAUX}
    resume = {
        "lance_le": lance_le.isoformat(timespec="seconds"), "durees_s": durees, "processus": processus,
        "commit": _git("rev-parse", "--short", "HEAD"), "commit_du_critere": COMMIT_DU_CRITERE,
        "code_agent_inchange": code_agent_inchange(),
        "empreinte_barres": donnees.empreinte(tickers, dossier), "titres": sorted(barres),
        "ecartes": {t: c.raisons for t, c in controles.items() if not c.utilisable},
        "controles": {t: {"barres": c.barres, "premiere": str(c.premiere), "derniere": str(c.derniere),
                          "sans_prix": c.sans_prix, "doublons": c.doublons, "trous": len(c.trous)}
                      for t, c in controles.items()},
        "derniere_barre": str(max(df.index[-1] for df in barres.values())),
        "memes_trades_entre_profils": all(len(set(v)) == 1 for v in par_capital.values()),
        "configurations": [{"capital": s.capital, "profil": s.profil, "ordres": len(s.ordres),
                            "ouvertes_a_la_fin": s.ouvertes_a_la_fin, "erreurs_agent": len(s.erreurs),
                            "premieres_erreurs": s.erreurs[:5],
                            "decisions": {f"{d} ({st})": n for (d, st), n in sorted(s.decisions.items())},
                            "refus": dict(s.refus.most_common())} for s in strategies],
        "neutralisees": [list(n) for n in enveloppe.NEUTRALISEES],
    }
    with open(os.path.join(dossier, "lancement.json"), "w", encoding="utf-8") as f:
        json.dump(resume, f, ensure_ascii=False, indent=1)
    if ecrire_rapport:
        from rejeu import rapport
        resume["rapport"] = rapport.ecrire(dossier, dossier_rapport, resume)
    return resume
