"""
tests/test_jev_fantome_dashboard.py — Ligne de comparaison fantôme Jev / paper du dashboard
(REGISTRE_CRITERES §8.3) : même fenêtre, coûts des deux côtés, inconnu ≠ 0, lecture seule,
rien d'autre que la valeur et le nombre de positions ouvertes.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_fantome_dashboard -v
Base SQLite temporaire, valeurs inventées, aucun réseau.
"""

import os
import sqlite3
import unittest

from tests.jev_fantome_fixtures import RACINE, BaseFantome  # en premier : variables de config.py
from utils import database, jev_paper_db
from utils.jev_db import connexion_lecture
from utils.jev_paper_comparaison import MENTION, comparaison


class BaseComparaison(BaseFantome):

    def fantome(self, ticker, jour, statut, pnl_net=None, prix=100.0, quantite=0.4, montant=40.0):
        conn = jev_paper_db.connexion()
        n = len(conn.execute("SELECT id FROM jev_paper_positions").fetchall())
        conn.execute("INSERT INTO jev_paper_positions (observation_id, ticker, statut, jour_entree, prix_entree, "
                     "quantite, montant_investi, pnl_net, horodatage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'x')",
                     (n + 1, ticker, statut, jour, prix, quantite, montant, pnl_net))
        conn.commit()
        conn.close()

    def paper(self, ticker, entree_le, direction="LONG", sortie=None, quantite=0.5, montant=50.0):
        from utils import portfolio_db as pdb
        pdb.initialiser_paper_db()
        pos = pdb.creer_position({"ticker": ticker, "direction": direction, "entry_price": 100.0,
                                  "entry_date": entree_le, "quantity": quantite, "invested_amount": montant,
                                  "stop_loss": 90.0, "target_1": 120.0})
        if sortie is not None:
            pdb.fermer_position(pos, sortie, "test", "CLOSED_TP")

    def lire_comparaison(self) -> dict:
        conn = connexion_lecture()
        try:
            return comparaison(conn)
        finally:
            conn.close()


class TestComparaison(BaseComparaison):

    def test_rien_avant_la_premiere_position_fantome(self):
        vide = {"mention": MENTION, "debut": None, "capital_depart": None, "fantome": None, "paper": None}
        self.assertEqual(self.lire_comparaison(), vide)  # tables du fantôme absentes
        jev_paper_db.connexion().close()
        self.assertEqual(self.lire_comparaison(), vide)  # tables vides

    def test_valeurs_meme_fenetre_et_couts_des_deux_cotes(self):
        self.fantome("SPY", "2026-11-02", "CLOSED", pnl_net=3.92)        # déjà net des coûts
        self.fantome("BTC-USD", "2026-11-03", "OPEN")                     # 0,4 à 100
        self.ajouter_barres("BTC-USD", {"2026-11-05": 105.0, "2026-11-06": 110.0})
        self.paper("VOO", "2026-10-20T07:30:00+00:00", sortie=110.0)      # avant la fenêtre : exclue
        self.paper("QQQ", "2026-11-02T07:30:00+00:00", sortie=104.0)      # réalisé brut +2,00
        self.paper("NVDA", "2026-11-03T07:30:00+00:00")                   # ouverte, LONG
        self.paper("SOL-USD", "2026-11-04T07:30:00+00:00", direction="SHORT", quantite=0.2, montant=20.0)
        self.ajouter_barres("NVDA", {"2026-11-06": 90.0})
        self.ajouter_barres("SOL-USD", {"2026-11-06": 95.0})
        c = self.lire_comparaison()
        self.assertEqual((c["debut"], c["capital_depart"], c["mention"]), ("2026-11-02", 1000.0, MENTION))
        # Fantôme : 1000 + 3,92 + (0,4 × 10 − 1 % × 40) = 1007,52
        self.assertEqual(c["fantome"], {"valeur": 1007.52, "positions_ouvertes": 1, "prix_manquants": []})
        # Paper : 1000 + (2 − 0,2 % × 50) + (−5 − 0,2 % × 50) + (0,2 × 5 − 1 % × 20) = 997,60
        self.assertEqual(c["paper"], {"valeur": 997.6, "positions_ouvertes": 2, "prix_manquants": []})

    def test_fenetre_au_jour_de_lisbonne(self):
        self.fantome("SPY", "2026-10-12", "CLOSED", pnl_net=0.0)
        self.paper("QQQ", "2026-10-11T23:30:00+00:00", sortie=102.0)  # 00h30 à Lisbonne le 12/10 : incluse
        self.paper("VOO", "2026-10-11T22:30:00+00:00", sortie=150.0)  # 23h30 à Lisbonne le 11/10 : exclue
        self.assertEqual(self.lire_comparaison()["paper"]["valeur"], round(1000 + 1.0 - 0.1, 2))

    def test_prix_manquant_valeur_inconnue_jamais_zero(self):
        self.fantome("SPY", "2026-11-02", "OPEN")
        self.paper("NVDA", "2026-11-03T07:30:00+00:00")
        c = self.lire_comparaison()
        self.assertEqual(c["fantome"], {"valeur": None, "positions_ouvertes": 1, "prix_manquants": ["SPY"]})
        self.assertEqual(c["paper"], {"valeur": None, "positions_ouvertes": 1, "prix_manquants": ["NVDA"]})

    def test_seulement_valeur_et_positions_ouvertes(self):
        self.fantome("SPY", "2026-11-02", "CLOSED", pnl_net=1.0)
        c = self.lire_comparaison()
        self.assertEqual(set(c), {"mention", "debut", "capital_depart", "fantome", "paper"})
        for cote in ("fantome", "paper"):
            self.assertEqual(set(c[cote]), {"valeur", "positions_ouvertes", "prix_manquants"})

    def test_lecture_seule(self):
        self.paper("QQQ", "2026-11-02T07:30:00+00:00")
        avant = os.path.getsize(database.DB_PATH), os.path.getmtime(database.DB_PATH)
        self.assertIsNone(self.lire_comparaison()["debut"])
        conn = sqlite3.connect(database.DB_PATH)
        try:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'jev_paper_%'").fetchone())
        finally:
            conn.close()
        self.assertEqual((os.path.getsize(database.DB_PATH), os.path.getmtime(database.DB_PATH)), avant)


class TestRoute(BaseComparaison):

    def setUp(self):
        super().setUp()
        from flask import Flask
        from dashboard.api.jev_fantome_routes import jev_fantome_api
        app = Flask(__name__)
        app.register_blueprint(jev_fantome_api)
        self.client = app.test_client()

    def test_get_seulement(self):
        self.fantome("SPY", "2026-11-02", "CLOSED", pnl_net=2.0)
        r = self.client.get("/api/jev/fantome")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json["mention"], r.json["fantome"]["valeur"]), (MENTION, 1002.0))
        for verbe in ("post", "put", "delete"):
            self.assertEqual(getattr(self.client, verbe)("/api/jev/fantome").status_code, 405)

    def test_page_overview_affiche_la_mention(self):
        with open(os.path.join(RACINE, "dashboard", "templates", "overview.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn(MENTION, page)
        self.assertIn('fetch("/api/jev/fantome")', page)


if __name__ == "__main__":
    unittest.main()
