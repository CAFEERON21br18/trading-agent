"""
tests/socle_fixtures.py — Grand livre temporaire et données inventées pour les tests du socle
(ledger, mesures, importeurs). Reprend tests/conftest.py de la source (pytest), mêmes valeurs.

Aucun réseau, aucun .env. Chaque base est créée dans un dossier temporaire, jamais dans data/.
Données entièrement fictives (règle 9).
"""

import math
import os
import tempfile
import unittest
from datetime import datetime, timezone

import ledger


def jour(j, h=10):
    return datetime(2030, 1, j, h, tzinfo=timezone.utc)


def ids_de_test(conn):
    """(compte, instrument) inventés : la fixture « ids » de la source."""
    return (ledger.compte(conn, "Test", "paper", "USD"),
            ledger.instrument(conn, "AAA", "USD"))


def trade(conn, ids, ref, sens="achat", q="10", prix="100", j=1, **kw):
    return ledger.enregistrer_trade(
        conn, compte_id=ids[0], instrument_id=ids[1], horodatage=jour(j),
        sens=sens, quantite=q, prix=prix, devise="USD", source="test",
        ref_source=ref, **kw)


class Proche:
    """Égalité approchée, avec la tolérance de pytest.approx (relative 1e-6, absolue 1e-12)."""

    def assertProche(self, obtenu, attendu):
        self.assertTrue(math.isclose(obtenu, attendu, rel_tol=1e-6, abs_tol=1e-12),
                        f"{obtenu!r} n'est pas proche de {attendu!r}")


class BaseLedger(unittest.TestCase):
    """Un grand livre neuf par test, dans un dossier temporaire : la fixture « conn » de la source."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.dossier.cleanup)
        self.conn = self.nouvelle_base("ledger.db")

    def nouvelle_base(self, nom):
        """Ouvre un autre grand livre neuf dans le dossier du test (un par cas d'un test paramétré)."""
        conn = ledger.ouvrir(os.path.join(self.dossier.name, nom))
        self.addCleanup(conn.close)  # fermé avant la suppression du dossier (ordre inverse)
        return conn


class BaseLedgerIds(BaseLedger):
    """Grand livre neuf avec le compte et l'instrument de test."""

    def setUp(self):
        super().setUp()
        self.ids = ids_de_test(self.conn)
