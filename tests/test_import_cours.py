"""
tests/test_import_cours.py — Clôtures quotidiennes vers le grand livre (importeurs/cours.py,
scripts/ledger_cours.py).

1. pour chaque instrument négocié : du jour de son premier trade jusqu'à la veille ; le jour en
   cours, un jour hors période et une valeur invalide ne sont pas enregistrés ;
2. relancer n'ajoute aucun doublon ; seuls les 7 derniers jours stockés sont redemandés ; une
   clôture corrigée par la source ajoute une ligne, la dernière saisie l'emporte ;
3. un symbole introuvable est listé et n'empêche pas les autres ;
4. à blanc : rien n'est écrit ; un premier trade plus ancien fait redemander le début ;
5. cloture_yfinance sur un faux module yfinance : clôture non ajustée, échecs convertis ;
6. script : à blanc par défaut (fichier du grand livre intact, table non créée), --appliquer
   écrit, sans grand livre rien n'est créé.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_import_cours -v
Source simulée, cours inventés, bases temporaires ; aucun réseau (toute connexion lève une erreur).
"""

import contextlib
import io
import os
import sys
import types
import unittest
from datetime import date
from decimal import Decimal as D
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from importeurs import cours as ic
from scripts import ledger_cours
from tests import socle_schema_8_tables
from tests.pro_fixtures import empreinte
from tests.socle_cours_fixtures import AUJOURD_HUI, j, source
from tests.socle_fixtures import BaseLedger, jour

AAA = [(j(2), 100.0), (j(3), 101.123456789), (j(6), float("nan")), (j(7), 0.0), (j(8), 104.0), (j(9), 105.5),
       (AUJOURD_HUI, 999.0), (j(1), 98.0)]
BBB = [(j(8), 20.25), (j(9), 20.5)]


class BaseCours(BaseLedger):
    def setUp(self):
        super().setUp()
        piege = mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))
        piege.start()
        self.addCleanup(piege.stop)
        self.compte = ledger.compte(self.conn, "Test", "reel", "EUR")
        self.n = 0

    def trade(self, symbole, jour_, devise="USD", sens="achat"):
        self.n += 1
        ledger.enregistrer_trade(
            self.conn, compte_id=self.compte, instrument_id=ledger.instrument(self.conn, symbole, devise),
            horodatage=jour(jour_), sens=sens, quantite="1", prix="100", devise=devise, source="test",
            ref_source=f"t{self.n}")
        self.conn.commit()

    def importer(self, telecharger, **kw):
        return ic.importer(self.conn, telecharger, aujourd_hui=AUJOURD_HUI, **kw)


class TestImporter(BaseCours):
    def test_du_premier_trade_a_la_veille_puis_aucun_doublon(self):
        self.trade("AAA", 2)
        self.trade("AAA", 5, sens="vente")
        self.trade("BBB.PA", 8, devise="EUR")
        src = source({"AAA": AAA, "BBB.PA": BBB})
        r = self.importer(src)
        self.assertEqual((r.instruments, r.ajoutes, r.deja_presents, r.ecartes, r.introuvables, r.a_jour),
                         (2, 6, 0, 2, [], []))
        self.assertEqual(src.appels, [("AAA", j(2), j(9)), ("BBB.PA", j(8), j(9))])
        self.assertEqual([(c.jour, c.cloture, c.devise, c.source) for c in ledger.cours(self.conn, "AAA")],
                         [(j(2), D("100"), "USD", "yfinance"), (j(3), D("101.12345679"), "USD", "yfinance"),
                          (j(8), D("104"), "USD", "yfinance"), (j(9), D("105.5"), "USD", "yfinance")])
        self.assertEqual(ledger.derniers_cours(self.conn)["BBB.PA"], ledger.Cours("BBB.PA", j(9), D("20.5"), "EUR",
                                                                                 "yfinance"))
        r = self.importer(src)  # relance : rien de plus
        self.assertEqual((r.ajoutes, r.deja_presents, r.ecartes), (0, 6, 2))
        self.assertEqual(src.appels[2:], [("AAA", j(2), j(9)), ("BBB.PA", j(8), j(9))])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cours").fetchone()[0], 6)

    def test_cloture_corrigee_et_recouvrement(self):
        self.trade("AAA", 1)
        self.importer(source({"AAA": [(date(2029, 12, 31), 90.0), (j(1), 98.0), (j(9), 105.5)]}))
        src = source({"AAA": [(j(9), 106.0), (j(10), 107.0), (j(11), 108.0)]})
        r = ic.importer(self.conn, src, aujourd_hui=j(12))
        self.assertEqual(src.appels, [("AAA", j(2), j(11))])  # 7 jours avant le dernier cours stocké
        self.assertEqual((r.ajoutes, r.deja_presents), (3, 0))
        self.assertEqual([(c.jour, c.cloture) for c in ledger.cours(self.conn, "AAA")],
                         [(j(1), D("98")), (j(9), D("106")), (j(10), D("107")), (j(11), D("108"))])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cours").fetchone()[0], 5)  # l'ancienne reste

    def test_symbole_introuvable_n_empeche_pas_les_autres(self):
        self.trade("AAA", 8)
        self.trade("ZZZ", 8)
        self.trade("BBB.PA", 10, devise="EUR")  # premier trade aujourd'hui : rien à demander
        r = self.importer(source({"AAA": AAA}))
        self.assertEqual((r.instruments, r.ajoutes, r.a_jour), (3, 2, ["BBB.PA"]))
        self.assertEqual(r.introuvables, [("ZZZ", "aucune barre entre 2030-01-08 et 2030-01-09")])
        self.assertEqual(set(ledger.derniers_cours(self.conn)), {"AAA"})

    def test_a_blanc_et_premier_trade_plus_ancien(self):
        self.trade("AAA", 8)
        self.assertEqual(self.importer(source({"AAA": AAA}), appliquer=False).ajoutes, 2)
        self.assertEqual(ledger.cours(self.conn), [])  # à blanc : rien n'est écrit
        self.importer(source({"AAA": AAA}))
        self.trade("AAA", 2)  # un relevé plus ancien importé après coup
        src = source({"AAA": AAA})
        r = self.importer(src)
        self.assertEqual((src.appels, r.ajoutes, r.deja_presents), ([("AAA", j(2), j(9))], 2, 2))


class TestClotureYfinance(unittest.TestCase):
    def appeler(self, history):
        demandes = []

        class Ticker:
            def __init__(self, symbole):
                demandes.append(symbole)

            def history(self, **kw):
                demandes.append(kw)
                return history()
        with mock.patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=Ticker)}), \
                mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau")):
            return ic.cloture_yfinance("BTC-USD", j(7), j(9)), demandes

    def test_barres_lues_non_ajustees_et_echecs_convertis(self):
        import pandas as pd
        index = pd.DatetimeIndex(["2030-01-07", "2030-01-08"], tz="America/New_York")
        barres, demandes = self.appeler(lambda: pd.DataFrame({"Close": [1.25, 1.26], "Adj Close": [1.0, 1.0]},
                                                             index=index))
        self.assertEqual(barres, [(j(7), 1.25), (j(8), 1.26)])
        self.assertEqual(demandes[0], "BTC-USD")
        self.assertEqual({c: demandes[1][c] for c in ("start", "end", "interval", "auto_adjust")},
                         {"start": "2030-01-07", "end": "2030-01-10", "interval": "1d", "auto_adjust": False})

        def en_panne():
            raise ConnectionError("réseau coupé")
        for history in (en_panne, lambda: pd.DataFrame(), lambda: None):
            with self.subTest(history=history), self.assertRaises(ic.SymboleIntrouvable):
                self.appeler(history)


class TestScript(BaseCours):
    def lancer(self, chemin, *args, telecharger=None):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = ledger_cours.lancer(chemin, "--appliquer" in args, telecharger, AUJOURD_HUI)
        return code, sortie.getvalue()

    def test_a_blanc_par_defaut_puis_appliquer(self):
        ancien = os.path.join(self.dossier.name, "ancien.db")
        conn = socle_schema_8_tables.creer_ancien(ancien)  # grand livre d'avant la table cours
        compte = ledger.compte(conn, "Paper agent", "paper", "EUR")
        for symbole in ("AAA", "ZZZ"):
            ledger.enregistrer_trade(conn, compte_id=compte, instrument_id=ledger.instrument(conn, symbole, "USD"),
                                     horodatage=jour(8), sens="achat", quantite="1", prix="100", devise="USD",
                                     source="test", ref_source=symbole)
        conn.commit()
        conn.close()
        avant = empreinte(ancien)
        code, texte = self.lancer(ancien, telecharger=source({"AAA": AAA}))
        self.assertEqual(code, 0)
        for attendu in ("À BLANC : rien n'a été écrit", "introuvable chez Yahoo : ZZZ"):
            self.assertIn(attendu, texte)
        self.assertRegex(texte, r"clôtures ajoutées +: 2\s")
        self.assertEqual(empreinte(ancien), avant)  # ni ligne ni table : le fichier n'a pas bougé
        code, texte = self.lancer(ancien, "--appliquer", telecharger=source({"AAA": AAA}))
        self.assertEqual((code, "Cours enregistrés." in texte), (0, True))
        lecture = ledger.ouvrir_lecture(ancien)
        self.addCleanup(lecture.close)
        self.assertEqual([c.cloture for c in ledger.cours(lecture, "AAA")], [D("104"), D("105.5")])

    def test_sans_grand_livre_ou_tout_introuvable(self):
        absent = os.path.join(self.dossier.name, "absent.db")
        code, texte = self.lancer(absent, "--appliquer", telecharger=source({}))
        self.assertEqual((code, "grand livre introuvable" in texte, os.path.exists(absent)), (1, True, False))
        self.trade("ZZZ", 8)
        self.conn.commit()
        code, texte = self.lancer(os.path.join(self.dossier.name, "ledger.db"), telecharger=source({}))
        self.assertEqual((code, "introuvable chez Yahoo : ZZZ" in texte), (1, True))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ledger_cours.main(["--ledger", absent]), 1)  # arguments lus, rien de créé


if __name__ == "__main__":
    unittest.main()
