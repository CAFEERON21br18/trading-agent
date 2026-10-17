"""
tests/test_rotation_fantome.py — TODO §17 : rotation v5 en OBSERVATION seulement. Slots pleins et
opportunité refusée : la position qu'elle aurait fermée va dans rotation_hypothetique ; aucune position
ni aucun cash ne change, slots pleins comme vides ; registre lu en mode=ro, jamais écrit ;
ROTATION_ACTIVE=1 refusé et journalisé.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rotation_fantome -v
Bases temporaires (paper et registre au vrai schéma), positions et décisions inventées, sans réseau.
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import config
from agents import rotation_fantome as rf
from agents.paper_trader.portfolio import etat_portefeuille
from utils import database
from utils.portfolio_db import initialiser_paper_db, lire_positions_ouvertes
from utils.registre_schema import COLONNES, GENESE, SCHEMA, _canon, empreinte_ligne

MAINTENANT = datetime(2026, 10, 19, 7, 45, tzinfo=timezone.utc)
# (horodatage, passage, ticker, décision, confiance, origine, résultat)
DECISIONS = [("2026-10-18T06:40:00+00:00", "veille", "OLD", "BUY", 10, "cycle", "refusee"),
             ("2026-10-19T06:40:00+00:00", "jour", "OPP1", "BUY", 9, "cycle", "refusee"),
             ("2026-10-19T06:40:01+00:00", "jour", "OPP2", "SELL", 7, "cycle", "refusee"),
             ("2026-10-19T06:40:02+00:00", "jour", "OPP3", "BUY", 9, "cycle", "ouverte"),
             ("2026-10-19T06:40:03+00:00", "jour", "OPP4", "BUY", 9, "conseiller", "refusee"),
             ("2026-10-19T06:40:04+00:00", "jour", "OPP5", "HOLD", 0, "cycle", "non_soumise")]


def registre(chemin: str) -> None:
    conn = sqlite3.connect(chemin)
    conn.executescript(SCHEMA)
    precedent = GENESE
    for h, passage, ticker, decision, conf, origine, resultat in DECISIONS:
        ligne = {"horodatage": h, "type": "decision", "cycle": "quotidien", "passage_id": passage, "ticker": ticker,
                 "decision": decision, "style": "normal", "score": 2.5, "confiance": conf, "prix": 100.0,
                 "position_id": None, "parametres": None, "version_code": "test", "hash_precedent": precedent,
                 "contenu": _canon({"origine": origine, "suite": {"resultat": resultat}})}
        precedent = empreinte_ligne(ligne)
        conn.execute(f"INSERT INTO registre ({', '.join(COLONNES)}, hash) VALUES ({', '.join('?' * (len(COLONNES) + 1))})",
                     [ligne[c] for c in COLONNES] + [precedent])
    conn.commit()
    conn.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.registre = os.path.join(self.dossier.name, "registre.db")
        registre(self.registre)
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "database.db")),
                       mock.patch.object(config, "MAX_POSITIONS_SIMULTANEES", 3),
                       mock.patch("agents.paper_trader.executor.fermer_position", side_effect=AssertionError("fermeture")),
                       mock.patch("utils.portfolio_db.fermer_position", side_effect=AssertionError("fermeture")),
                       mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")),
                       mock.patch("curl_cffi.requests.Session.request", side_effect=AssertionError("aucun réseau"))]
        for p in self.patchs:
            p.start()
        initialiser_paper_db()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()

    def positions(self, *confiances):
        conn = database.get_connection()
        for i, c in enumerate(confiances):
            conn.execute("INSERT INTO positions (ticker, direction, status, entry_price, entry_date, quantity, "
                         "invested_amount, stop_loss, target_1, confidence) VALUES (?, 'LONG', 'OPEN', 10, "
                         "'2026-10-10', 2, 20, 9, 12, ?)", (f"POS{i}", c))
        conn.commit()
        conn.close()

    def etat(self):
        e = etat_portefeuille(with_live_prices=False)  # sans cours en direct : aucun réseau
        with open(self.registre, "rb") as f:
            return (lire_positions_ouvertes(), e["cash"], e["invested"], hashlib.sha256(f.read()).hexdigest())

    def propositions(self):
        conn = database.get_connection()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM rotation_hypothetique")]
        except sqlite3.OperationalError:
            return []  # table jamais créée
        finally:
            conn.close()


class TestFantome(Base):
    def test_slots_pleins_proposition_enregistree_rien_ne_change(self):
        self.positions(8, 6, 7)  # la plus faible : confiance 6
        avant = self.etat()
        self.assertEqual(rf.observer_cycle(MAINTENANT, self.registre), 1)
        self.assertEqual(self.etat(), avant)  # positions, cash, investi et registre identiques
        (p,) = self.propositions()
        self.assertEqual((p["jour"], p["cycle"], p["passage_id"], p["position_ticker"], p["position_confiance"],
                          p["opportunite_ticker"], p["opportunite_decision"], p["opportunite_confiance"],
                          p["ecart_confiance"]), ("2026-10-19", "quotidien", "jour", "POS1", 6, "OPP1", "BUY", 9, 3))
        self.assertEqual(rf.observer_cycle(MAINTENANT, self.registre), 0)  # même passage : pas de doublon
        self.assertEqual(len(self.propositions()), 1)

    def test_slots_vides_rien_ne_change(self):
        self.positions(8, 6)
        avant = self.etat()
        self.assertEqual(rf.observer_cycle(MAINTENANT, self.registre), 0)
        self.assertEqual((self.etat(), self.propositions()), (avant, []))

    def test_aucun_passage_du_jour(self):
        self.positions(8, 6, 7)
        lendemain = datetime(2026, 10, 20, 7, 45, tzinfo=timezone.utc)
        self.assertEqual(rf.observer_cycle(lendemain, self.registre), 0)

    def test_activation_refusee_et_journalisee(self):
        self.positions(8, 6, 7)
        avant = self.etat()
        with mock.patch.object(config, "ROTATION_ACTIVE", True), \
             self.assertLogs("agents.rotation_fantome", level="ERROR") as journal:
            rf.observer_cycle(MAINTENANT, self.registre)
        self.assertIn("activation non autorisée : critère du registre requis", journal.output[0])
        self.assertEqual(self.etat(), avant)

    def test_interrupteur_a_zero_par_defaut(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROTATION_ACTIVE", None)
            self.assertFalse(config._get_optional("ROTATION_ACTIVE", "0").strip().lower() in ("1", "true", "oui", "yes"))
        with open(os.path.join(RACINE, "config.py"), encoding="utf-8") as f:
            self.assertIn('ROTATION_ACTIVE  = _get_optional("ROTATION_ACTIVE", "0")', f.read())


if __name__ == "__main__":
    unittest.main()
