"""
tests/test_jev_fantome_page.py — Page « Fantôme Jev » du dashboard (REGISTRE_CRITERES §8.3,
v1.5) : routes GET seulement (405 sinon), base inchangée, prix manquant jamais 0, tri du
bloc 3, date de sortie prévue = celle du fantôme, en-tête cohérent avec les blocs.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_fantome_page -v
Base SQLite temporaire, valeurs inventées, aucun réseau.
"""

import hashlib
import os
import sqlite3
import unittest

from tests.jev_fantome_fixtures import RACINE, BaseFantome, observation  # en premier : variables de config.py
from utils import database
from utils.jev_db import connexion_lecture
from utils.jev_fantome_page import date_sortie_prevue, page
from utils.jev_paper_comparaison import MENTION

SEMAINE = {f"2026-11-{j:02d}": 100.0 + j - 1 for j in (2, 3, 4, 5, 6)}  # SPY : 101 … 105, lun. → ven.
CLES_BLOC_3 = {"ticker", "statut", "choix", "p_acheter", "conviction_niveau", "regime_jev", "regime_moteur",
               "decision_moteur", "fantome"}


class BasePage(BaseFantome):

    def lire_page(self) -> dict:
        conn = connexion_lecture()
        try:
            return page(conn)
        finally:
            conn.close()

    def portefeuille(self) -> None:
        """SPY acheté le 02/11 et fermé le 09/11 à 105 ; NVDA ouverte (dernière clôture 103)."""
        self.ajouter_obs(observation("SPY", "2026-11-02", p_acheter=0.9),
                         observation("NVDA", "2026-11-02", p_acheter=0.8))
        self.ajouter_barres("SPY", SEMAINE)
        self.ajouter_barres("NVDA", {"2026-11-02": 102.0, "2026-11-03": 103.0})
        self.lancer("2026-11-02")


class TestBlocsPositions(BasePage):

    def test_ouvertes_fermees_et_en_tete_coherents(self):
        self.portefeuille()
        avant = {o["ticker"]: o["sortie"] for o in self.lire_page()["ouvertes"]["positions"]}
        self.assertEqual(avant["SPY"], {"barre": "2026-11-06", "estimee": False})  # avant sa sortie
        self.lancer("2026-11-09")
        p = self.lire_page()
        nvda, = p["ouvertes"]["positions"]
        # 0,4 × (103 − 100) − 0,2 % × 40 = 1,12 (coûts du §7.1 déduits, comme l'en-tête)
        self.assertEqual((nvda["ticker"], nvda["groupe"], nvda["dernier_prix"], nvda["jour_dernier_prix"]),
                         ("NVDA", "SEMIS_IA", 103.0, "2026-11-03"))
        self.assertEqual((nvda["pnl_latent"], nvda["pnl_latent_pct"]), (1.12, 2.8))
        self.assertEqual(nvda["sortie"], {"barre": "2026-11-06", "estimee": True})
        spy, = p["fermees"]["positions"]
        # 0,4 × (105 − 100) − 0,08 = 1,92 ; sortie à la 5e barre, celle annoncée quand elle était ouverte
        self.assertEqual((spy["barre_sortie"], spy["prix_sortie"], spy["pnl_net"], spy["pnl_pct"]),
                         ("2026-11-06", 105.0, 1.92, 4.8))
        self.assertEqual(p["fermees"]["total"], {"positions": 1, "montant_investi": 40.0, "pnl": 1.92,
                                                 "pnl_pct": 4.8})
        e = p["entete"]
        self.assertEqual((e["positions_ouvertes"], e["positions_fermees"]), (1, 1))
        self.assertEqual(e["fantome"]["valeur"],
                         round(1000 + p["fermees"]["total"]["pnl"] + p["ouvertes"]["total"]["pnl"], 2))

    def test_prix_manquant_jamais_zero(self):
        self.ajouter_obs(observation("BTC-USD", "2026-11-07"))  # samedi, aucune barre en base
        self.lancer("2026-11-07")
        p = self.lire_page()
        btc, = p["ouvertes"]["positions"]
        for cle in ("dernier_prix", "jour_dernier_prix", "pnl_latent", "pnl_latent_pct"):
            self.assertIsNone(btc[cle], cle)
        self.assertEqual(btc["sortie"], {"barre": "2026-11-11", "estimee": True})  # crypto : jours calendaires
        self.assertIsNone(p["ouvertes"]["total"]["pnl"])
        self.assertEqual((p["entete"]["fantome"]["valeur"], p["entete"]["fantome"]["prix_manquants"]),
                         (None, ["BTC-USD"]))
        with open(os.path.join(RACINE, "dashboard", "templates", "fantome_jev.html"), encoding="utf-8") as f:
            gabarit = f.read()
        self.assertIn('const ND = "non disponible"', gabarit)
        for couleur in ("emerald", "green", "red-"):  # pas de couleur de gain ou de perte
            self.assertNotIn(couleur, gabarit)

    def test_date_sortie_prevue(self):
        cinq = [(j, c) for j, c in SEMAINE.items()]
        self.assertEqual(date_sortie_prevue(cinq, "2026-11-02", "SPY"), {"barre": "2026-11-06", "estimee": False})
        self.assertEqual(date_sortie_prevue([("2026-11-06", 1.0)], "2026-11-06", "SPY"),
                         {"barre": "2026-11-12", "estimee": True})   # week-end sauté
        self.assertEqual(date_sortie_prevue([], "2026-11-07", "GC=F"), {"barre": "2026-11-13", "estimee": True})
        self.assertEqual(date_sortie_prevue([], "2026-11-07", "ETH-USD"), {"barre": "2026-11-11", "estimee": True})

    def test_mention_avec_date_de_lecture(self):
        self.assertEqual(self.lire_page()["mention"], MENTION)  # aucune observation
        self.portefeuille()
        # 02/11/2026 + 12 semaines + 10 jours (§7.2, comme scripts/jev_bilan.py)
        self.assertEqual(self.lire_page()["mention"], f"{MENTION} — lecture le 04/02/2027")


class TestBlocObservations(BasePage):

    def test_tri_et_action_du_fantome(self):
        self.ajouter_obs(observation("SPY", "2026-11-02", p_acheter=0.99),  # jour précédent : absent
                         observation("MSFT", "2026-11-03", p_acheter=0.3, action_jev="ne_rien_faire"),
                         observation("AMD", "2026-11-03", p_acheter=0.9, action_jev="acheter"),
                         observation("CL=F", "2026-11-03", p_acheter=None, statut="erreur"),
                         observation("TSLA", "2026-11-03", p_acheter=0.65, position_ouverte=1),
                         observation("AAPL", "2026-11-03", p_acheter=0.9),
                         observation("GC=F", "2026-11-03", p_acheter=0.6))
        self.lancer("2026-11-03")
        self.ajouter_obs(observation("VOO", "2026-11-03", p_acheter=0.8,
                                     horodatage="2026-11-03T08:00:00+00:00"))  # après le passage du fantôme
        j = self.lire_page()["jour"]
        self.assertEqual(j["jour"], "2026-11-03")
        self.assertEqual([a["ticker"] for a in j["actifs"]], ["AAPL", "AMD", "VOO", "TSLA", "GC=F", "MSFT", "CL=F"])
        fantome = {a["ticker"]: (a["fantome"]["action"], a["fantome"]["motif"]) for a in j["actifs"]}
        self.assertEqual(fantome, {"AAPL": ("achat", None), "AMD": ("achat", None), "VOO": ("en_attente", None),
                                   "TSLA": ("refus", "position_paper_ouverte"), "GC=F": ("achat", None),
                                   "MSFT": ("pas_candidat", None), "CL=F": ("hors_observation", "erreur")})
        self.assertEqual(j["actifs"][1]["choix"], "acheter")
        for a in j["actifs"]:  # §8.3 : ni prix ni rendement pour les observations
            self.assertEqual(set(a), CLES_BLOC_3)

    def test_sans_observation(self):
        self.assertEqual(self.lire_page()["jour"], {"jour": None, "actifs": []})


class TestRoutes(BasePage):

    def setUp(self):
        super().setUp()
        from flask import Flask
        from dashboard.api.jev_fantome_routes import jev_fantome_api, jev_fantome_page
        app = Flask(__name__, template_folder=os.path.join(RACINE, "dashboard", "templates"))
        app.register_blueprint(jev_fantome_api)
        app.register_blueprint(jev_fantome_page)
        self.client = app.test_client()

    def empreinte(self) -> tuple:
        """Contenu et date du fichier, et taille du -wal. La base est en WAL : une lecture
        mode=ro peut créer -shm et un -wal vide, mais toute écriture ajouterait des trames au -wal."""
        with open(self.chemin, "rb") as f:
            contenu = hashlib.sha256(f.read()).hexdigest()
        wal = self.chemin + "-wal"
        return contenu, os.path.getmtime(self.chemin), os.path.getsize(wal) if os.path.exists(wal) else 0

    def test_get_seulement(self):
        self.portefeuille()
        r = self.client.get("/api/jev/fantome/detail")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json), {"mention", "entete", "ouvertes", "fermees", "jour"})
        r = self.client.get("/fantome-jev")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn(MENTION, html)
        self.assertIn('fetch("/api/jev/fantome/detail")', html)
        self.assertIn('href="/fantome-jev"', html)  # lien du menu
        for url in ("/fantome-jev", "/api/jev/fantome/detail", "/api/jev/fantome"):
            for verbe in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, verbe)(url).status_code, 405, f"{verbe} {url}")

    def test_base_inchangee_apres_appel(self):
        self.portefeuille()
        avant = self.empreinte()
        for url in ("/api/jev/fantome/detail", "/fantome-jev", "/api/jev/fantome"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.empreinte(), avant)

    def test_tables_du_fantome_jamais_creees(self):
        self.ajouter_obs(observation("SPY", "2026-11-02"))
        avant = self.empreinte()
        r = self.client.get("/api/jev/fantome/detail")
        self.assertEqual((r.status_code, r.json["ouvertes"]["positions"]), (200, []))
        self.assertEqual(self.empreinte(), avant)
        conn = sqlite3.connect(database.DB_PATH)
        try:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'jev_paper_%'").fetchone())
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
