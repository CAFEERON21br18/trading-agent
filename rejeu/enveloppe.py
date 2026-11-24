"""
rejeu/enveloppe.py — Ce qui entoure l'agent pendant le rejeu, sans modifier un seul de ses fichiers.

Le moteur appelle les vraies fonctions de l'agent. Ce qu'elles iraient chercher en production
(base de la tour, heure courante, cours en ligne, e-mails, LLM) est remplacé ICI, le temps du
rejeu, puis remis en place. Deux sortes de remplacements :
- NEUTRALISEES : des entrées de la décision rendues neutres, parce que le critère (registre §10)
  ne teste que l'analyste technique. Elles sont listées dans le rapport ;
- des enveloppes techniques : base jetable de data/rejeu/, horloge du rejeu, barres du passé,
  réglages épinglés (rejeu/parametres.py). Elles ne changent aucune règle.
Garde-fous : toute tentative de connexion réseau, d'appel à un LLM ou d'envoi d'e-mail lève une
erreur ; les erreurs que l'agent journalise sont comptées (un rejeu propre n'en a aucune).
"""

import logging
from contextlib import ExitStack, contextmanager
from datetime import datetime, time, timedelta, timezone
from unittest import mock

import numpy as np
import pandas as pd

from rejeu import parametres as P

NEUTRE = "neutralisé par le rejeu"
NEUTRALISEES = [
    ("Analyste fondamental", "direction NEUTRE, confiance 0 (agents.asset_analyzer._fondamental)"),
    ("Analyste de sentiment (news)", "direction NEUTRE, confiance 0 (agents.asset_analyzer._sentiment)"),
    ("Fear & Greed, dominance BTC, corrélation BTC/SPY", "contexte global absent : le veto Fear & Greed ne joue jamais"),
    ("Mémoire (winrate par actif, leçons, patterns)", "vide : ni veto « track record », ni winrate dans l'allocation (50 % par défaut)"),
    ("Intuition", "aucun ajustement, aucun override, rien d'écrit dans intuition_log.md"),
    ("Régime de marché", "absent du contexte (il ne sert qu'à la note de qualité du setup)"),
    ("Contrôle de liquidité de la note de qualité du setup", "tenu pour bon : cette note est une annotation, "
     "aucune règle d'ouverture ne la lit"),
    ("Audit métacognitif et pipeline de raisonnement (LLM)", "non exécutés : le moteur est appelé par son chemin "
     "sans LLM (origine « chat ») ; le pipeline ne réduit donc jamais la taille"),
    ("Trailing stop", "jamais activé : il ne s'active en production que par une action manuelle"),
    ("Prix frais (barre de 1 minute)", "remplacé par l'ouverture de la barre quotidienne suivante"),
    ("E-mails et registre des décisions", "aucun e-mail envoyé, rien d'écrit dans le registre"),
]


class AppelInterdit(RuntimeError):
    """Le rejeu a tenté de sortir de son enveloppe (réseau, LLM, e-mail)."""


class Contexte:
    """Ce que les enveloppes lisent : l'horloge du rejeu, les analyses déjà calculées, le jour des
    données de chaque titre (sa dernière barre close), les prix d'ouverture du jour."""

    def __init__(self, analyses: dict):
        self.analyses, self.jour_donnees, self.ouvertures, self.clotures = analyses, {}, {}, {}
        self.instant, self._tic, self.erreurs = None, 0, []

    def fixer(self, jour, heure: int) -> None:
        self.instant, self._tic = datetime.combine(jour, time(heure), tzinfo=timezone.utc), 0

    def iso(self) -> str:
        """Horodatage de l'agent : l'instant du rejeu, une seconde plus tard à chaque écriture
        (les lectures « les plus récentes d'abord » de l'agent restent ainsi ordonnées)."""
        self._tic += 1
        return (self.instant + timedelta(seconds=self._tic)).isoformat(timespec="seconds")

    def analyse(self, ticker: str):
        return self.analyses.get(ticker, {}).get(self.jour_donnees.get(ticker))


def _interdit(quoi: str):
    def refuser(*a, **k):
        raise AppelInterdit(f"{quoi} : interdit pendant le rejeu")
    return refuser


class _Compteur(logging.Handler):
    def __init__(self, ctx):
        super().__init__(logging.ERROR)
        self.ctx = ctx

    def emit(self, record):
        self.ctx.erreurs.append(f"{record.name} : {record.getMessage()[:160]}")


@contextmanager
def agent_enveloppe(ctx: Contexte, capital: float, chemin_base: str):
    """Met l'agent dans le rejeu : base jetable, horloge, analyses du passé, réglages épinglés."""
    import config
    import smtplib
    from agents import asset_analyzer, decision_engine, intuition
    from agents.analysts.risk_manager import manager as risque
    from agents.paper_trader import anti_boucle, cycle, executor, portfolio
    from agents.technical_skills import liquidity, market_regime
    from utils import database, gemini, llm, portfolio_db

    def barres_du_passe(ticker, timeframe="1d", limite=P.BARRES_SCORE):
        a = ctx.analyse(ticker)
        if a is None or a.niveaux is None:
            return pd.DataFrame()  # l'agent dit alors « données absentes » et refuse
        df = pd.DataFrame({"atr": [np.nan if a.atr is None else a.atr]})
        df.attrs["ticker"] = ticker
        return df

    class Maintenant(datetime):
        @classmethod
        def now(cls, tz=None):
            return ctx.instant

    reglages = dict(P.CONFIG_AGENT, CAPITAL=float(capital), EXCLURE_BOUCLES_STATS=0,
                    CAPITAL_INVESTISSABLE=capital * P.CONFIG_AGENT["MAX_CAPITAL_INVESTI_PCT"] / 100,
                    CASH_RESERVE=capital * (1 - P.CONFIG_AGENT["MAX_CAPITAL_INVESTI_PCT"] / 100),
                    RISK_PER_TRADE_EUR=capital * P.CONFIG_AGENT["RISK_PER_TRADE_PCT"] / 100,
                    CAPITAL_STOP_THRESHOLD=capital * P.PART_SEUIL_ARRET)
    remplacements = [
        (database, "DB_PATH", chemin_base),
        # entrées neutralisées (NEUTRALISEES)
        (asset_analyzer, "_fondamental", lambda t: {"direction": "NEUTRE", "confiance": 0, "evaluation": NEUTRE, "detail": NEUTRE}),
        (asset_analyzer, "_sentiment", lambda t, nb_news=5: {"direction": "NEUTRE", "confiance": 0, "narratif": NEUTRE, "detail": NEUTRE}),
        (asset_analyzer, "consulter_memoire", lambda t: {"perf": None, "lecons": [], "patterns": []}),
        (market_regime, "dernier_regime", lambda *a, **k: None),
        (liquidity, "liquidite_suffisante", lambda *a, **k: True),
        (intuition, "consulter_intuition", lambda t, analyses, decision: {
            "ajustement": 0, "pressentiment": "neutre", "raisons": [], "override_decision": None, "boost_confiance": 0}),
        (intuition, "journaliser_intuition", lambda *a, **k: None),
        (executor, "envoyer_email", lambda *a, **k: False),
        # enveloppes techniques : résultats des vraies fonctions, calculés sur les barres du passé
        (asset_analyzer, "_technique", lambda t: dict(ctx.analyse(t).technique)),
        (risque, "charger_ohlcv", barres_du_passe),
        (risque, "calculer_tous_indicateurs", lambda df: df),
        (risque, "detecter_niveaux_cles", lambda df: ctx.analyse(df.attrs["ticker"]).niveaux),
        (cycle, "prix_frais", lambda t: (ctx.ouvertures[t], 0.0) if t in ctx.ouvertures else None),
        (portfolio, "prix_actuel", lambda t: ctx.clotures.get(t)),
        (portfolio_db, "_now_iso", ctx.iso),
        (anti_boucle, "datetime", Maintenant),
        (decision_engine, "SEUIL_BUY", P.SEUIL_BUY), (decision_engine, "SEUIL_SELL", P.SEUIL_SELL),
        # garde-fous
        (llm, "ask_llm", _interdit("appel LLM")), (gemini, "ask_gemini", _interdit("appel Gemini")),
        (smtplib, "SMTP", _interdit("e-mail")), (smtplib, "SMTP_SSL", _interdit("e-mail")),
    ] + [(config, nom, valeur) for nom, valeur in reglages.items()]
    compteur = _Compteur(ctx)
    with ExitStack() as pile:
        for cible, nom, valeur in remplacements:
            pile.enter_context(mock.patch.object(cible, nom, valeur))
        pile.enter_context(mock.patch("socket.socket.connect", _interdit("connexion réseau")))
        logging.getLogger().addHandler(compteur)
        logging.disable(logging.WARNING)  # les journaux de l'agent ne reçoivent que les erreurs
        try:
            portfolio_db.initialiser_paper_db()
            yield ctx
        finally:
            logging.disable(logging.NOTSET)
            logging.getLogger().removeHandler(compteur)
