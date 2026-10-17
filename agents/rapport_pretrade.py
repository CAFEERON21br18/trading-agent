"""
agents/rapport_pretrade.py — Analyse pré-trade condensée dans le rapport quotidien (TODO §17).

AFFICHAGE SEULEMENT : section du rapport et de l'email de agents/orchestrator.py, construite après les
décisions, ouvertures, fermetures et Jev ; aucune décision, ni le chat, ni le registre ne la lisent.
Seulement les actifs qui ont reçu un BUY ou un SELL du cycle. Par actif :
- 1. Graphique : agents/knowledge/chart_reading.analyser_graphique (5 couches, barres en base) ;
- 3. Catalyseurs : non implémentés, « non disponible » (jamais un contenu inventé) ;
- 7. Risque et 8. Synthèse : agents/knowledge/pretrade_analysis (mode condensé).
Aucun des deux modules n'appelle un LLM ; aucune requête réseau (cours lus dans la table prices).
Un actif en erreur affiche « non disponible » ; les autres sont rendus.
"""

from agents.knowledge.chart_reading import analyser_graphique
from agents.knowledge.pretrade_analysis import CATALYSEURS, analyse_pretrade
from utils.logger import get_logger

logger = get_logger(__name__)

NON_DISPO = "non disponible"


def _f(v) -> str:
    return NON_DISPO if v is None else f"{v:.2f}"


def _graphique(ticker: str) -> str:
    g = analyser_graphique(ticker, "1d")
    if "erreur" in g:
        return NON_DISPO
    s = g["structure"]
    return (f"{s['tendance']} | {s['phase']} | weekly : {g['mtf']['weekly']} | confluence "
            f"{g['score_confluence']}/10 ({len(g['elements_confluence'])} élément(s))")


def bloc_actif(d: dict) -> str:
    """Bloc markdown d'un actif BUY ou SELL ({ticker, decision, analyses} de la routine)."""
    dec, ticker = d["decision"], d["ticker"]
    a = analyse_pretrade(ticker, d["analyses"], dec, mode="condense")
    s7, s8 = a.get("7_gestion_risque") or {}, a["8_synthese"]
    try:
        graphique = _graphique(ticker)
    except Exception as e:
        logger.warning(f"Pré-trade {ticker} : lecture graphique non disponible ({e})")
        graphique = NON_DISPO
    risque = (f"entrée {_f(s7.get('entree'))} | SL {_f(s7.get('stop_loss'))} | R:R {_f(s7.get('rr_1'))}"
              if s7 else NON_DISPO)
    return "\n".join([f"### {ticker} — {s8['decision']} ({s8['conviction']}/10) [{s8['style']}]",
                      f"- **1. Graphique** : {graphique}",
                      f"- **3. Catalyseurs** : {a['3_catalyseurs']['prochains_catalyseurs']}",
                      f"- **7. Risque** : {risque}",
                      f"- **8. Synthèse** : {s8['thèse'] or NON_DISPO}"])


def section_pretrade(decisions: list[dict]) -> str:
    """Section du rapport, ou "" sans BUY ni SELL dans le cycle."""
    actifs = [d for d in decisions if d["decision"]["decision"] in ("BUY", "SELL")]
    if not actifs:
        return ""
    blocs = []
    for d in actifs:
        try:
            blocs.append(bloc_actif(d))
        except Exception as e:
            logger.warning(f"Pré-trade {d.get('ticker')} : {e}")
            blocs.append(f"### {d.get('ticker')} — {NON_DISPO}")
    return ("\n## 🔎 Analyse pré-trade condensée (BUY et SELL du cycle)\n\n"
            "_Affichage seulement : aucune décision ne lit cette section. Catalyseurs : "
            f"{CATALYSEURS}._\n\n" + "\n\n".join(blocs) + "\n")
