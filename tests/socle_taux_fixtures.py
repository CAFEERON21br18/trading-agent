"""
tests/socle_taux_fixtures.py — Source de cours simulée et piège réseau pour les tests du taux EURUSD
du socle (importeurs/taux_change.py, scripts/ledger_taux.py). Taux inventés, aucun réseau.
"""

from datetime import date
from unittest import mock

from importeurs import taux_change as tc
from tests.socle_fixtures import BaseLedger

AUJOURD_HUI = date(2030, 1, 10)
COURS = [(date(2030, 1, 7), 1.25), (date(2030, 1, 8), 1.2512345678), (date(2030, 1, 9), 1.26)]


def source(cours=COURS):
    """Source simulée : rend les cours donnés et note les périodes demandées."""
    appels = []

    def telecharger(debut, fin):
        appels.append((debut, fin))
        return list(cours)
    telecharger.appels = appels
    return telecharger


class SansReseau(BaseLedger):
    def setUp(self):
        super().setUp()
        piege = mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))
        piege.start()
        self.addCleanup(piege.stop)

    def importer(self, cours=COURS, debut=date(2030, 1, 1), fin=date(2030, 1, 31), **kw):
        return tc.importer(self.conn, debut, fin, source(cours), aujourd_hui=AUJOURD_HUI, **kw)
