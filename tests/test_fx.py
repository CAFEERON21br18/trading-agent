"""
tests/test_fx.py — Taux de change du portefeuille réel (utils/fx.py) : yfinance simulé, en succès
et en échec. Un échec rend None, jamais 1.0 ; « non disponible » à l'affichage.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_fx -v
Sans réseau ni base ; taux inventé de 1,25 ; logs redirigés hors de logs/.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from scripts._banc_fichiers import journaux_detaches
_LOGS = tempfile.mkdtemp()
_JOURNAUX = journaux_detaches(_LOGS)
_JOURNAUX.__enter__()  # tout le module : aucun message dans logs/ (production)

from tests.fx_fixtures import HEURE, faux_yfinance
from utils.fx import NON_DISPO, en_eur, libelle_taux, taux_eur


def tearDownModule():
    _JOURNAUX.__exit__(None, None, None)
    shutil.rmtree(_LOGS, ignore_errors=True)


class TestTauxEur(unittest.TestCase):
    def test_succes(self):
        with faux_yfinance(1.25) as appels:
            info = taux_eur("USD")
            self.assertEqual(info, {"taux": 1.25, "source": "EURUSD=X", "horodatage": HEURE.isoformat()})
            self.assertEqual(en_eur(125.0, "usd"), (100.0, info))
        self.assertEqual(appels, ["EURUSD=X"])  # le second appel vient du cache
        self.assertRegex(libelle_taux(info), r"^EURUSD=X 1,2500 \(14/10 \d\dh30\)$")

    def test_devise_absente_vaut_usd(self):
        with faux_yfinance(1.25) as appels:
            self.assertEqual(taux_eur(None)["source"], "EURUSD=X")
        self.assertEqual(appels, ["EURUSD=X"])

    def test_echec_reseau_rend_none_jamais_un(self):
        with faux_yfinance(erreur=OSError("réseau coupé")):
            self.assertIsNone(taux_eur("USD"))
            self.assertEqual(en_eur(125.0, "USD"), (None, None))
        self.assertEqual(libelle_taux(None), NON_DISPO)
        self.assertEqual(NON_DISPO, "non disponible")

    def test_cours_vide_nan_nul_ou_negatif(self):
        for taux in (None, float("nan"), float("inf"), 0.0, -1.25):
            with faux_yfinance(taux):
                self.assertIsNone(taux_eur("USD"), taux)

    def test_echec_jamais_garde_en_cache(self):
        with faux_yfinance(erreur=OSError("réseau coupé")):
            self.assertIsNone(taux_eur("USD"))
            from utils import fx
            self.assertEqual(fx._cache, {})
        with faux_yfinance(1.25) as appels:
            self.assertEqual(taux_eur("USD")["taux"], 1.25)
        self.assertEqual(appels, ["EURUSD=X"])

    def test_euro_sans_conversion_ni_appel(self):
        with faux_yfinance(erreur=OSError("ne doit pas être appelé")) as appels:
            info = taux_eur("EUR")
        self.assertEqual(appels, [])
        self.assertEqual(info["taux"], 1.0)
        self.assertEqual(libelle_taux(info), "EUR, sans conversion")

    def test_devise_invalide(self):
        with faux_yfinance(1.25) as appels:
            self.assertIsNone(taux_eur("US"))
            self.assertIsNone(taux_eur("U$D"))
        self.assertEqual(appels, [])

    def test_libelle_virgule_decimale_seulement_sur_le_taux(self):
        info = {"taux": 1.08, "source": "EURGBP=X", "horodatage": HEURE.isoformat()}
        self.assertTrue(re.match(r"^EURGBP=X 1,0800 \(", libelle_taux(info)))


if __name__ == "__main__":
    unittest.main()
