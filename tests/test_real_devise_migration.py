"""
tests/test_real_devise_migration.py — Migration de la colonne devise (scripts/migrer_devise_reelle.py) :
à blanc par défaut sans aucune écriture, sauvegarde avant toute écriture, défaut 'USD', idempotente,
et prompt du chat identique à l'octet avant et après la migration.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_real_devise_migration -v
Bases temporaires, valeurs inventées (règle 9) ; logs redirigés hors de logs/.
"""

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from scripts._banc_fichiers import journaux_detaches
_LOGS = tempfile.mkdtemp()
_JOURNAUX = journaux_detaches(_LOGS)
_JOURNAUX.__enter__()  # tout le module : aucun message dans logs/ (production)

from scripts import migrer_devise_reelle as m
from utils import database
from utils import real_portfolio_db as db

SCHEMA = ("CREATE TABLE real_investments (id INTEGER PRIMARY KEY AUTOINCREMENT, asset TEXT NOT NULL, "
          "entry_price REAL NOT NULL, quantity REAL NOT NULL, invested_amount REAL NOT NULL, "
          "status TEXT DEFAULT 'OPEN')")
LIGNES = [("AAA", 50.0, 2.0, 100.0), ("BBB", 12.5, 10.0, 125.0)]


def tearDownModule():
    _JOURNAUX.__exit__(None, None, None)
    shutil.rmtree(_LOGS, ignore_errors=True)


def octets(chemin: str) -> str:
    with open(chemin, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class BaseTemporaire(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = os.path.join(self.dossier.name, "database.db")
        self.sauv = os.path.join(self.dossier.name, "sauvegardes")

    def tearDown(self):
        self.dossier.cleanup()

    def creer_base(self):
        conn = sqlite3.connect(self.base)
        conn.execute(SCHEMA)
        conn.executemany("INSERT INTO real_investments (asset, entry_price, quantity, invested_amount) "
                         "VALUES (?, ?, ?, ?)", LIGNES)
        conn.commit()
        conn.close()


class TestMigration(BaseTemporaire):
    def setUp(self):
        super().setUp()
        self.creer_base()

    def test_a_blanc_par_defaut_n_ecrit_rien(self):
        avant, mtime = octets(self.base), os.path.getmtime(self.base)
        r = m.migrer(self.base, dossier_sauvegarde=self.sauv)
        self.assertEqual(r["action"], "à blanc")
        self.assertIn("ajouterait la colonne devise ('USD') à 2 ligne(s)", r["raison"])
        self.assertEqual(octets(self.base), avant)
        self.assertEqual(os.path.getmtime(self.base), mtime)
        self.assertFalse(os.path.exists(self.sauv))  # pas même le dossier des sauvegardes
        self.assertEqual(os.listdir(self.dossier.name), ["database.db"])  # ni -journal, ni -wal
        self.assertFalse(m.etat(self.base)["colonne"])

    def test_ligne_de_commande_a_blanc_par_defaut(self):
        avant = octets(self.base)
        with mock.patch("builtins.print"):
            self.assertEqual(m.main(["--base", self.base, "--sauvegardes", self.sauv]), 0)
        self.assertEqual(octets(self.base), avant)
        self.assertFalse(os.path.exists(self.sauv))

    def test_appliquer_sauvegarde_d_abord_puis_colonne_usd(self):
        avant = octets(self.base)
        r = m.migrer(self.base, appliquer=True, dossier_sauvegarde=self.sauv)
        self.assertEqual(r["action"], "appliquée")
        self.assertTrue(r["controle_ok"])
        self.assertEqual(os.path.dirname(r["sauvegarde"]), self.sauv)
        # la sauvegarde est la base d'avant : sans la colonne, mêmes lignes, intègre
        self.assertEqual(m.etat(r["sauvegarde"]), {"table": True, "colonne": False, "lignes": 2, "integrite": "ok"})
        self.assertNotEqual(octets(self.base), avant)
        conn = sqlite3.connect(self.base)
        try:
            self.assertEqual(conn.execute("SELECT asset, devise FROM real_investments ORDER BY id").fetchall(),
                             [("AAA", "USD"), ("BBB", "USD")])
            conn.execute("INSERT INTO real_investments (asset, entry_price, quantity, invested_amount) "
                         "VALUES ('CCC', 1.0, 1.0, 1.0)")  # une saisie sans devise prend le défaut
            self.assertEqual(conn.execute("SELECT devise FROM real_investments WHERE asset = 'CCC'").fetchone()[0],
                             "USD")
        finally:
            conn.close()

    def test_idempotente(self):
        m.migrer(self.base, appliquer=True, dossier_sauvegarde=self.sauv)
        apres, sauvegardes = octets(self.base), sorted(os.listdir(self.sauv))
        for appliquer in (True, False):
            r = m.migrer(self.base, appliquer=appliquer, dossier_sauvegarde=self.sauv)
            self.assertEqual(r["action"], "aucune")
            self.assertEqual(r["raison"], "colonne devise déjà présente")
        self.assertEqual(octets(self.base), apres)
        self.assertEqual(sorted(os.listdir(self.sauv)), sauvegardes)  # aucune nouvelle sauvegarde

    def test_base_absente_jamais_creee(self):
        absente = os.path.join(self.dossier.name, "absente.db")
        with self.assertRaises(FileNotFoundError):
            m.migrer(absente, appliquer=True, dossier_sauvegarde=self.sauv)
        self.assertFalse(os.path.exists(absente))
        self.assertFalse(os.path.exists(self.sauv))


class TestAvecLeSchemaDuCode(BaseTemporaire):
    """Schéma créé par initialiser_real_db, comme en production."""

    def setUp(self):
        super().setUp()
        self.patch = mock.patch.object(database, "DB_PATH", self.base)
        self.patch.start()
        db.initialiser_real_db()
        self.plan = db.creer_plan({"name": "Plan inventé", "plan_type": "long_terme",
                                   "objective": "objectif inventé", "allocated_budget": 300.0})
        for asset, entry, qty, inv in LIGNES:
            db.ajouter_investissement({"asset": asset, "holding_type": "moyen", "instrument_type": "normal",
                                       "entry_price": entry, "quantity": qty, "invested_amount": inv,
                                       "plan_id": self.plan})

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_devise_lue_apres_migration(self):
        self.assertNotIn("devise", db.lire_investissements()[0])  # avant : colonne absente
        m.migrer(self.base, appliquer=True, dossier_sauvegarde=self.sauv)
        self.assertEqual({p["devise"] for p in db.lire_investissements()}, {"USD"})

    def test_prompt_du_chat_identique_a_l_octet_apres_migration(self):
        from agents.chat._formatters import formater_real_status
        from agents.chat._llm import _construire_prompt

        def prompt() -> str:
            ctx = {"real_resume": db.resume_portefeuille(), "real_open": db.lire_investissements(filtre_status="OPEN"),
                   "real_advice": []}
            return _construire_prompt("Où en est mon portefeuille réel ?", "real_status",
                                      formater_real_status(ctx), ctx)

        avant = prompt()
        self.assertIn("== PORTEFEUILLE RÉEL ==", avant)
        self.assertIn("Plan inventé", avant)  # lire_plan() a bien été lu dans la base
        m.migrer(self.base, appliquer=True, dossier_sauvegarde=self.sauv)
        self.assertEqual(prompt().encode("utf-8"), avant.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
