"""
rejeu/moteur.py — Le rejeu, jour par jour, d'une configuration (un capital, un profil de frais).

Chaque jour J, dans cet ordre :
1. OUVERTURE de J : les fermetures décidées la veille (signal inverse) sont exécutées à
   l'ouverture ; puis les décisions BUY/SELL de la veille passent par le vrai circuit du paper
   trader (anti-boucle, Budget Manager, Risk Manager, porte d'entrée), au prix d'ouverture de J ;
2. SÉANCE de J : stop et objectif de chaque position testés sur le haut et le bas de la barre
   (rejeu/sorties.py), y compris pour une position ouverte le matin même ;
3. CLÔTURE de J : analyse de chaque titre avec les seules barres jusqu'à J, vraie décision du
   moteur de l'agent, vraie réévaluation des positions ouvertes ; les ordres partent à
   l'ouverture de la barre suivante du titre ;
4. valeur du compte à la clôture : capital, résultat net réalisé, résultat latent, frais.
Les règles de l'agent voient des résultats BRUTS, comme en production (il ne compte aucun
frais) ; les frais sont comptés à côté, dans la valeur du compte et dans chaque ordre.
"""

import os
import re
from datetime import date
from decimal import Decimal

from rejeu import frais, sorties
from rejeu import parametres as P
from rejeu.enveloppe import Contexte, agent_enveloppe
from rejeu.resultat import STRATEGIE, Ordre, Resultat

HEURE_OUVERTURE, HEURE_SEANCE, HEURE_CLOTURE = 8, 12, 22  # repères de l'horloge du rejeu (UTC)


def motif(raison: str) -> str:
    """Motif de refus sans ses chiffres ni son titre, pour les compter."""
    raison = re.sub(r" sur [A-Z0-9=.^-]+$", "", str(raison))
    return re.sub(r"[-+]?\d+(?:[.,]\d+)?", "n", raison)[:70]


def _jour(pos: dict) -> date:
    return date.fromisoformat(str(pos["entry_date"])[:10])


def _latent(positions: list, ctx: Contexte, profil: str, jour: date) -> Decimal:
    total = Decimal(0)
    for p in positions:
        cours = ctx.clotures.get(p["ticker"], p["entry_price"])
        ecart = cours - p["entry_price"] if p["direction"] == "LONG" else p["entry_price"] - cours
        total += frais.decimal(ecart * p["quantity"])
        total -= frais.financement(profil, p["quantity"] * p["entry_price"], _jour(p), jour)
    return total


def simuler(capital: int, profil: str, barres: dict, analyses: dict, chemin_base: str,
            fin: date | None = None) -> Resultat:
    """Rejoue la configuration sur toutes les barres à partir du 01/01/2018 (jusqu'à `fin`).

    chemin_base : base SQLite JETABLE de l'agent pour cette configuration (effacée d'abord).
    """
    for suffixe in ("", "-wal", "-shm"):
        if os.path.exists(chemin_base + suffixe):
            os.remove(chemin_base + suffixe)
    os.makedirs(os.path.dirname(chemin_base), exist_ok=True)
    lignes = {t: df.to_dict("index") for t, df in barres.items()}
    calendrier = sorted({j for t in lignes for j in lignes[t] if j >= P.DEBUT_REJEU and (fin is None or j <= fin)})
    ctx, res, realise = Contexte(analyses), Resultat(STRATEGIE, capital, profil), Decimal(0)
    pendantes, a_fermer = {}, {}

    with agent_enveloppe(ctx, capital, chemin_base):
        from agents.asset_analyzer import analyser_actif_complet
        from agents.decision_engine import decider, reevaluer_position
        from agents.paper_trader.cycle import executer_ouvertures
        from agents.paper_trader.executor import fermer_position
        from utils.portfolio_db import lire_position_ouverte_actif, lire_positions_ouvertes

        def fermer(pos: dict, prix: float, raison: str, statut: str, jour: date) -> Decimal:
            brut = fermer_position(pos["id"], prix, raison, statut)["pnl_euros"]
            couts = frais.sortie(profil, pos["ticker"], pos["quantity"], prix, pos["entry_price"], _jour(pos), jour)
            res.ordres.append(Ordre(f"pos{pos['id']}-sortie", pos["ticker"], ctx.instant,
                                    "vente" if pos["direction"] == "LONG" else "achat",
                                    pos["quantity"], prix, tuple(couts), statut=statut))
            return frais.decimal(brut) - frais.total(couts)

        for jour in calendrier:
            du_jour = {t: lignes[t][jour] for t in barres if jour in lignes[t]}
            # 1. ouverture : fermetures décidées la veille, puis ouvertures par le circuit de l'agent
            ctx.fixer(jour, HEURE_OUVERTURE)
            ctx.ouvertures = {t: b["Open"] for t, b in du_jour.items()}
            for pos in lire_positions_ouvertes():
                if pos["ticker"] in a_fermer and pos["ticker"] in du_jour:
                    realise += fermer(pos, du_jour[pos["ticker"]]["Open"], a_fermer.pop(pos["ticker"]),
                                      "CLOSED_REVERSAL", jour)
            for t in du_jour:
                a_fermer.pop(t, None)  # une fermeture non exécutée ne survit pas à sa barre
            lot = [pendantes.pop(t) for t in list(pendantes) if t in du_jour]
            if lot:
                bilan = executer_ouvertures(lot)
                styles = {d["ticker"]: d["decision"].get("style", "normal") for d in lot}
                for o in bilan["ouvertes"]:
                    pos = lire_position_ouverte_actif(o["ticker"])
                    couts = frais.entree(profil, pos["ticker"], pos["quantity"], pos["entry_price"])
                    res.ordres.append(Ordre(f"pos{pos['id']}-entree", pos["ticker"], ctx.instant,
                                            "achat" if pos["direction"] == "LONG" else "vente", pos["quantity"],
                                            pos["entry_price"], tuple(couts), stop=pos["stop_loss"],
                                            style=styles[pos["ticker"]]))
                    realise -= frais.total(couts)
                for refus in bilan["refusees"]:
                    res.refus[motif((refus.get("raisons") or ["raison inconnue"])[0])] += 1
            # 2. séance : stop et objectif sur le haut et le bas de la barre
            ctx.fixer(jour, HEURE_SEANCE)
            for pos in lire_positions_ouvertes():
                b = du_jour.get(pos["ticker"])
                s = b and sorties.tester(pos["direction"], pos["stop_loss"], pos["target_1"], b["Open"], b["High"],
                                         b["Low"], b["Close"], entree_ce_jour=_jour(pos) == jour)
                if s:
                    realise += fermer(pos, s.prix, s.raison, s.statut, jour)
            # 3. clôture : analyses avec les seules barres jusqu'à ce jour, décisions, réévaluations
            ctx.fixer(jour, HEURE_CLOTURE)
            for t, b in du_jour.items():
                ctx.jour_donnees[t], ctx.clotures[t] = jour, b["Close"]
            ouvertes = {p["ticker"]: p for p in lire_positions_ouvertes()}
            for t in du_jour:
                if ctx.analyse(t) is None:
                    continue
                vues = analyser_actif_complet(t)
                decision = decider(t, vues, origine="chat")  # chemin du moteur sans LLM
                res.decisions[(decision["decision"], decision.get("style", "normal"))] += 1
                if t in ouvertes:
                    verdict = reevaluer_position(ouvertes[t], vues)
                    if verdict["action"] == "CLOSE":
                        a_fermer[t] = verdict["raison"]
                if decision["decision"] in ("BUY", "SELL"):
                    pendantes[t] = {"ticker": t, "decision": decision, "analyses": vues}
                else:
                    pendantes.pop(t, None)
            # 4. valeur du compte à la clôture
            res.valeurs.append((jour, Decimal(capital) + realise + _latent(list(ouvertes.values()), ctx, profil, jour)))
        res.ouvertes_a_la_fin = len(lire_positions_ouvertes())
    res.erreurs = list(ctx.erreurs)
    return res
