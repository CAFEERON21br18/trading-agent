"""
agents/fundamental_analyst/macro.py — Données macroéconomiques
Sources gratuites : FRED (Federal Reserve Economic Data, pas de clé requise pour le niveau de base)
Fallback : données stockées en BDD via fetch_data.py (DXY, yields via yfinance si dispo)
"""

import sys
import os
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from utils.logger   import get_logger
from utils.database import get_connection

logger = get_logger(__name__)

# FRED — Federal Reserve Economic Data. Les séries "historical" sont accessibles sans clé
# via des URLs directes en CSV sur fred.stlouisfed.org
FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Séries macro clés
SERIES_FRED = {
    "DGS10":    "US 10Y Treasury Yield",
    "DGS2":     "US 2Y Treasury Yield",
    "DFF":      "Fed Funds Rate",
}


def recuperer_serie_fred(serie_id: str, jours: int = 30) -> float | None:
    """
    Récupère la dernière valeur d'une série FRED via le CSV public.
    Retourne la valeur la plus récente disponible (float) ou None.
    """
    try:
        date_debut = (datetime.now() - timedelta(days=jours)).strftime("%Y-%m-%d")
        params = {"id": serie_id, "cosd": date_debut}
        r = requests.get(FRED_CSV_BASE, params=params, timeout=15)
        r.raise_for_status()

        lignes = r.text.strip().split("\n")
        # Première ligne = header "DATE,VALEUR"
        # On prend la dernière ligne non vide avec une valeur numérique
        for ligne in reversed(lignes[1:]):
            parties = ligne.split(",")
            if len(parties) == 2 and parties[1] not in (".", ""):
                try:
                    return float(parties[1])
                except ValueError:
                    continue
        return None

    except Exception as e:
        logger.error(f"Erreur FRED {serie_id} : {e}")
        return None


def recuperer_contexte_macro() -> dict:
    """
    Récupère les indicateurs macro clés.
    Retourne un dict : {dgs10, dgs2, dff, courbe_2_10, interpretation}
    """
    dgs10 = recuperer_serie_fred("DGS10")
    dgs2  = recuperer_serie_fred("DGS2")
    dff   = recuperer_serie_fred("DFF")

    courbe = None
    if dgs10 is not None and dgs2 is not None:
        courbe = dgs10 - dgs2

    # Interprétation de la courbe
    if courbe is None:
        interp = "Données courbe indisponibles"
    elif courbe < 0:
        interp = f"Courbe inversée ({courbe:.2f}) — signal récession historique"
    elif courbe < 0.5:
        interp = f"Courbe très plate ({courbe:.2f}) — risque ralentissement"
    else:
        interp = f"Courbe normale (+{courbe:.2f}) — conditions financières saines"

    return {
        "us_10y":         dgs10,
        "us_2y":          dgs2,
        "fed_funds_rate": dff,
        "courbe_2_10":    courbe,
        "interpretation": interp,
    }


def recuperer_prix_dernier(ticker: str, timeframe: str = "1d") -> float | None:
    """Lit le dernier prix de clôture depuis la BDD SQLite."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT close FROM prices
            WHERE ticker = ? AND timeframe = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (ticker, timeframe))
        row = cursor.fetchone()
        conn.close()
        return float(row["close"]) if row else None
    except Exception as e:
        logger.error(f"Erreur lecture prix {ticker} : {e}")
        return None


def position_52_semaines(ticker: str) -> dict:
    """
    Calcule où se situe le prix actuel dans sa range 52 semaines.
    Utile pour les actions où on n'a pas les ratios fondamentaux.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MIN(low) AS low_52, MAX(high) AS high_52, close
            FROM (
                SELECT * FROM prices
                WHERE ticker = ? AND timeframe = '1d'
                ORDER BY timestamp DESC LIMIT 252
            )
        """, (ticker,))
        row = cursor.fetchone()

        cursor.execute("""
            SELECT close FROM prices
            WHERE ticker = ? AND timeframe = '1d'
            ORDER BY timestamp DESC LIMIT 1
        """, (ticker,))
        prix_row = cursor.fetchone()
        conn.close()

        if not row or not prix_row:
            return {}

        low_52  = float(row["low_52"])
        high_52 = float(row["high_52"])
        prix    = float(prix_row["close"])
        position_pct = (prix - low_52) / (high_52 - low_52) * 100

        return {
            "prix":        prix,
            "low_52":      low_52,
            "high_52":     high_52,
            "position_pct": position_pct,
        }
    except Exception as e:
        logger.error(f"Erreur position 52 semaines {ticker} : {e}")
        return {}
