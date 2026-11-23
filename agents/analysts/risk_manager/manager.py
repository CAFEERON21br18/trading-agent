"""
agents/risk_manager/manager.py — Sous-agent 4 : Risk Manager
Filtre final avant transmission d'un signal à l'utilisateur.
Applique les règles : R:R min, seuil d'arrêt capital, corrélations, disclaimer.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import config
from utils.logger     import get_logger
from utils.indicators import charger_ohlcv, calculer_tous_indicateurs, detecter_niveaux_cles
from agents.analysts.risk_manager.position_sizer import (
    calculer_stop_loss, calculer_targets, calculer_taille_position, calculer_rr,
)
from agents.analysts.risk_manager.rapport import formater_rapport_risque  # noqa: F401 — réexport

logger = get_logger(__name__)

RR_MINIMUM = 1.2  # v4.1 : 1:1.2 minimum (avant 1:2.0) — plus permissif pour apprendre

# Groupes d'actifs fortement corrélés (identifiés en Phase 3.6)
GROUPES_CORRELES = {
    "crypto_majors": {"BTC-USD", "ETH-USD", "SOL-USD"},
    "us_indices":    {"SPY", "QQQ", "VOO", "NQ=F"},
}


def verifier_capital_minimum() -> tuple[bool, str]:
    """Vérifie que le capital est au-dessus du seuil d'arrêt d'urgence."""
    if config.CAPITAL <= config.CAPITAL_STOP_THRESHOLD:
        return False, (
            f"Capital ({config.CAPITAL:.0f}€) ≤ seuil d'arrêt "
            f"({config.CAPITAL_STOP_THRESHOLD:.0f}€) — signaux suspendus"
        )
    return True, ""


def analyser_correlation_portefeuille(ticker: str, positions_ouvertes: set[str]) -> str | None:
    """
    Vérifie si ajouter ce ticker créerait une sur-exposition sur un facteur corrélé.
    Retourne un message d'avertissement ou None si OK.
    """
    for nom_groupe, tickers in GROUPES_CORRELES.items():
        if ticker in tickers:
            deja_dans_groupe = positions_ouvertes & tickers
            if deja_dans_groupe:
                return (
                    f"Positions déjà ouvertes sur actifs corrélés ({nom_groupe}) : "
                    f"{', '.join(deja_dans_groupe)}. Corrélations >0.9 = triple exposition."
                )
    return None


def valider_signal(ticker: str, direction: str, prix_entree: float,
                   timeframe: str = "1d",
                   positions_ouvertes: set[str] = None,
                   cash_disponible: float | None = None,
                   nb_positions_visees: int = 1,
                   budget_alloue: float | None = None) -> dict:
    """
    Valide un signal complet : calcule stop/targets/taille et applique toutes les règles.

    Retourne un dict :
      - valide : bool
      - signal : dict complet (si valide)
      - rejets : list[str] (raisons si invalide)
      - avertissements : list[str]
    """
    rejets = []
    avertissements = []
    positions_ouvertes = positions_ouvertes or set()

    # ── Vérification capital minimum ─────────────────────────────────────────
    ok, msg = verifier_capital_minimum()
    if not ok:
        rejets.append(msg)

    # ── Vérification direction valide ────────────────────────────────────────
    if direction not in ("LONG", "SHORT"):
        rejets.append(f"Direction invalide : {direction} (doit être LONG ou SHORT)")

    # ── Chargement des données et calcul ATR / niveaux ──────────────────────
    df = charger_ohlcv(ticker, timeframe)
    if df.empty:
        rejets.append(f"Données BDD absentes pour {ticker} [{timeframe}]")
        return {"valide": False, "rejets": rejets, "avertissements": avertissements}

    df      = calculer_tous_indicateurs(df)
    atr_raw = df["atr"].iloc[-1] if "atr" in df.columns else None
    atr     = float(atr_raw) if atr_raw is not None and not np.isnan(atr_raw) else prix_entree * 0.02

    niveaux     = detecter_niveaux_cles(df)
    support     = niveaux["supports"][0] if niveaux["supports"] else None
    resistance  = niveaux["resistances"][0] if niveaux["resistances"] else None

    # ── Calcul stop-loss et targets ──────────────────────────────────────────
    stop_loss = calculer_stop_loss(prix_entree, direction, atr, support, resistance)
    target_1, target_2 = calculer_targets(prix_entree, stop_loss, direction)

    rr_1 = calculer_rr(prix_entree, stop_loss, target_1, direction)
    rr_2 = calculer_rr(prix_entree, stop_loss, target_2, direction)

    if rr_1 is None:  # Phase 4 : veto conservé, avec la raison exacte (pas « R:R 0.00 »)
        rejets.append(f"Données de prix manquantes pour {ticker} [{timeframe}] : R:R non calculable")
    elif rr_1 < RR_MINIMUM:
        rejets.append(f"R:R insuffisant : {rr_1:.2f} < {RR_MINIMUM} (minimum requis)")

    # ── Calcul de la taille de position ─────────────────────────────────────
    position = calculer_taille_position(
        capital_total=config.CAPITAL,
        risque_pct=config.RISK_PER_TRADE_PCT,
        prix_entree=prix_entree,
        stop_loss=stop_loss,
        cash_disponible=cash_disponible,
        nb_positions_visees=nb_positions_visees,
        max_invested_pct=config.MAX_CAPITAL_INVESTI_PCT,
        budget_alloue=budget_alloue,
    )

    # ── Corrélation portefeuille ─────────────────────────────────────────────
    avert_corr = analyser_correlation_portefeuille(ticker, positions_ouvertes)
    if avert_corr:
        avertissements.append(avert_corr)

    # ── Résultat ─────────────────────────────────────────────────────────────
    if rejets:
        return {"valide": False, "rejets": rejets, "avertissements": avertissements}

    return {
        "valide":         True,
        "rejets":         [],
        "avertissements": avertissements,
        "signal": {
            "ticker":           ticker,
            "direction":        direction,
            "prix_entree":      prix_entree,
            "stop_loss":        stop_loss,
            "target_1":         target_1,
            "target_2":         target_2,
            "rr_1":             rr_1,
            "rr_2":             rr_2,
            "atr":              atr,
            "support_utilise":  support,
            "taille_unites":            position["taille_unites"],
            "montant_investi":          position["montant_investi"],
            "montant_risque_theorique": position["montant_risque_theorique"],
            "montant_risque_reel":      position["montant_risque_reel"],
            "limite_active":            position["limite_active"],
            "budget_par_position":      position["budget_par_position"],
            "capital_investissable":    position["capital_investissable"],
            "distance_stop":            position["distance_stop"],
        },
    }


if __name__ == "__main__":
    print("\nAlphaSignal — Risk Manager — Test\n")
    print("─── TEST 1 : LONG BTC-USD ───")
    print(formater_rapport_risque(valider_signal("BTC-USD", "LONG", 75000.0, nb_positions_visees=1)))
    print("\n─── TEST 2 : 3 positions visées (AAPL) ───")
    print(formater_rapport_risque(valider_signal("AAPL", "LONG", 265.0, nb_positions_visees=3)))
    print("\n─── TEST 3 : SHORT AAPL ───")
    print(formater_rapport_risque(valider_signal("AAPL", "SHORT", 265.0)))
