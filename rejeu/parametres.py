"""
rejeu/parametres.py — TOUS les paramètres du rejeu, dans ce seul fichier.

Critère : docs/REGISTRE_CRITERES.md §10, commité avant tout code de rejeu. Après le premier
lancement, aucune valeur de ce fichier ne change (un bogue corrigé est décrit dans
docs/REJEU_JOURNAL.md, tout est relancé, les résultats d'avant sont conservés).
"""

import os
from datetime import date
from decimal import Decimal

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "data", "rejeu")  # hors git ; seul endroit où le rejeu écrit des données
DOSSIER_RAPPORT = os.path.join(RACINE, "reports", "rejeu")  # hors git
UNIVERS = os.path.join(RACINE, "data", "watchlist.json.exemple")  # liste suivie par git, pas celle de la tour

# ── Période ───────────────────────────────────────────────────────────────────
DEBUT_DONNEES = date(2017, 1, 1)  # l'année 2017 ne sert qu'à amorcer les indicateurs
DEBUT_REJEU = date(2018, 1, 1)  # première décision possible : clôture du premier jour de 2018
ANNEES = tuple(range(2018, 2026))  # années civiles complètes du verdict
FIN_PERIODE = date(2025, 12, 31)  # 2026, partielle, est rapportée à part

# ── Configurations : 3 capitaux × 2 profils de frais ; une seule décide ───────
CAPITAUX = (100, 1000, 10000)  # euros
CONFIG_QUI_DECIDE = (1000, "revolut")

# ── Frais ─────────────────────────────────────────────────────────────────────
# « Revolut » : 1 € par ordre (achat comme vente). Valeur OBSERVÉE sur un relevé ; à confirmer
# contre la grille tarifaire.
# « CFD » : HYPOTHÈSES, à remplacer par des écarts mesurés sur un compte démo. Écart payé à
# chaque côté, en part du montant de l'ordre ; financement par nuit, en part du montant de la
# position à l'entrée, pour chaque nuit entre le jour d'entrée et le jour de sortie.
# Les contrats à terme (GC=F, NQ=F, CL=F) ne sont pas cités par la consigne : ils reçoivent
# l'écart le plus élevé, celui des cryptos (choix qui désavantage la stratégie).
PROFILS = {
    "revolut": {"libelle": "Revolut", "par_ordre": Decimal("1"), "ecart": {}, "financement_par_nuit": Decimal("0")},
    "cfd": {"libelle": "CFD", "par_ordre": Decimal("0"),
            "ecart": {"action": Decimal("0.0010"), "etf": Decimal("0.0010"),
                      "crypto": Decimal("0.0050"), "cfd": Decimal("0.0050")},
            "financement_par_nuit": Decimal("0.0002")},
}
# Le paper trader compte 1 € = 1 $ (TODO §29) : le rejeu fait de même. Capital en euros, cours en
# dollars pris pour des euros, aucun effet de change ; stratégie et référence sont logées à la
# même enseigne.
DEVISE = "EUR"

# ── Réglages de l'agent, épinglés aux valeurs par défaut du code (config.py) ──
# Le .env de la tour peut en changer certains (20 positions simultanées au lieu de 5) : le rejeu
# teste « ceux du code », quel que soit le .env de la machine qui le lance.
CONFIG_AGENT = {
    "RISK_PER_TRADE_PCT": 2.0, "MAX_CAPITAL_INVESTI_PCT": 50.0, "MAX_POSITIONS_SIMULTANEES": 5,
    "SEUIL_CONFIANCE_PAPER": 8, "SEUIL_CONFIANCE_PAPER_DEFENSIF": 9, "SEUIL_CONFIANCE_LEARNING": 4,
}
SEUIL_BUY, SEUIL_SELL = 2.0, -2.0
# Seuil d'arrêt d'urgence : 700 € pour 1 000 € dans le code. Gardé en proportion du capital
# (70 %) pour les capitaux de 100 € et 10 000 € ; pour 1 000 €, c'est la valeur du code.
PART_SEUIL_ARRET = 0.70
CAPITAL_DU_CODE = 1000.0

# ── Mesure ────────────────────────────────────────────────────────────────────
MIN_TRADES = 100  # en dessous, sur la période : « non décidable »
TIRAGES = 10_000  # bootstrap de l'espérance nette par trade
GRAINE = 20261124  # graine fixe : date du critère
CONFIANCE = 0.95

# ── Données ───────────────────────────────────────────────────────────────────
TROU_MAX = 5  # jours de bourse (lundi au vendredi) entre deux barres ; au-delà : un trou
# Un titre est INUTILISABLE, donc écarté et nommé dans le rapport, s'il a un prix nul ou négatif,
# une date en double, un trou de plus de TROU_MAX jours de bourse, ou moins de BARRES_MIN barres.
BARRES_MIN = 250
BARRES_SCORE = 500  # barres lues par l'agent pour son score technique (charger_ohlcv, limite=500)
