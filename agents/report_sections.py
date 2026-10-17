"""
agents/report_sections.py — Sections News et Fondamentaux du rapport quotidien (TODO §17).

AFFICHAGE seulement : rapport et email de agents/orchestrator.py, via agents/rapport_annexes.py ; aucune
décision, ni le chat, ni le registre ne les lisent. Seulement les actifs BUY ou SELL du cycle (décisions
du Decision Engine : {ticker, decision, analyses}).
- News : NewsAPI seulement, 1 requête par actif et MAX_REQUETES_JOUR au plus par jour de Lisbonne,
  comptées dans data/rapport_newsapi.json (toutes routines du jour confondues). Clé absente, plafond
  atteint, erreur ou réponse vide : « non disponible ». Pas de repli sur Yahoo RSS.
- Fondamentaux : analyses["fondamental"], déjà calculé par le cycle du jour (il n'existe pas de table de
  fondamentaux en base) : aucun nouvel appel Alpha Vantage (quota épuisé, TODO §27).
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from utils.logger import get_logger

logger = get_logger(__name__)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPTEUR = os.path.join(RACINE, "data", "rapport_newsapi.json")
MAX_REQUETES_JOUR = 10
NB_PAR_ACTIF = 3
NON_DISPO = "non disponible"
SANS_DONNEES = ("", "N/A", "Erreur", "Données indisponibles")
EMOJI_IMPACT = {"positif": "🟢", "négatif": "🔴", "neutre": "⚪"}


def _actifs(decisions: list[dict]) -> list[dict]:
    return [d for d in decisions if (d.get("decision") or {}).get("decision") in ("BUY", "SELL")]


def _entete(dec: dict) -> str:
    return f"### {dec['ticker']} — {dec['decision']} ({dec['confidence']}/10)"


def _jour() -> str:
    return datetime.now(ZoneInfo("Europe/Lisbon")).date().isoformat()


def _requetes_du_jour(jour: str) -> int:
    try:
        with open(COMPTEUR, encoding="utf-8") as f:
            c = json.load(f)
        return int(c.get("requetes", 0)) if c.get("jour") == jour else 0
    except FileNotFoundError:
        return 0
    except Exception as e:
        logger.warning(f"Compteur NewsAPI du rapport illisible ({e}) : repart de 0")
        return 0


def _noter(jour: str, n: int) -> None:
    os.makedirs(os.path.dirname(COMPTEUR), exist_ok=True)
    with open(COMPTEUR, "w", encoding="utf-8") as f:
        json.dump({"jour": jour, "requetes": n}, f)


def _lignes_news(news: list[dict]) -> list[str]:
    out = []
    for n in news:
        titre = n.get("titre") or ""
        titre = titre[:120] + "…" if len(titre) > 120 else titre
        out.append(f"- {EMOJI_IMPACT.get(n.get('impact'), '')} {titre} — _{n.get('source') or '?'}_")
    return out


def section_news(decisions: list[dict]) -> str:
    """Section News, ou "" sans BUY ni SELL."""
    actifs = _actifs(decisions)
    if not actifs:
        return ""
    from agents.analysts.sentiment_analyst.news_fetcher import recuperer_news_newsapi
    jour = _jour()
    faites = _requetes_du_jour(jour)
    blocs = []
    for d in actifs:
        dec = d["decision"]
        if not config.NEWSAPI_KEY or faites >= MAX_REQUETES_JOUR:
            raison = "clé NewsAPI absente" if not config.NEWSAPI_KEY else f"plafond de {MAX_REQUETES_JOUR} requêtes du jour"
            blocs.append(f"{_entete(dec)}\n- {NON_DISPO} ({raison})")
            continue
        faites += 1
        _noter(jour, faites)  # compté avant l'appel : un essai en échec compte aussi
        try:
            news = recuperer_news_newsapi(dec["ticker"], NB_PAR_ACTIF)
        except Exception as e:
            logger.warning(f"News du rapport {dec['ticker']} : {e}")
            news = []
        blocs.append("\n".join([_entete(dec)] + (_lignes_news(news) or [f"- {NON_DISPO}"])))
    return ("\n## 📰 News (NewsAPI, BUY et SELL du cycle)\n\n"
            "_Affichage seulement : aucune décision ne lit cette section._\n\n" + "\n\n".join(blocs) + "\n")


def section_fondamentaux(decisions: list[dict]) -> str:
    """Section Fondamentaux (analyse déjà faite par le cycle), ou "" sans BUY ni SELL."""
    actifs = _actifs(decisions)
    if not actifs:
        return ""
    blocs = []
    for d in actifs:
        f = (d.get("analyses") or {}).get("fondamental") or {}
        evaluation = str(f.get("evaluation") or "").strip()
        if evaluation in SANS_DONNEES:
            ligne = f"- {NON_DISPO}"
        else:
            ligne = (f"- Évaluation : {evaluation} | direction {f.get('direction') or '?'} | "
                     f"confiance {f.get('confiance', 0)}/10")
        blocs.append(f"{_entete(d['decision'])}\n{ligne}")
    return ("\n## 🏢 Fondamentaux (analyse du cycle, BUY et SELL)\n\n"
            "_Affichage seulement ; aucun nouvel appel Alpha Vantage (quota, TODO §27)._\n\n"
            + "\n\n".join(blocs) + "\n")
