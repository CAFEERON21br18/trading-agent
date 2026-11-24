"""
tests/test_rejeu_donnees.py — Données du rejeu (rejeu/donnees.py, scripts/rejeu_donnees.py).

1. univers : les titres de data/watchlist.json.exemple, avec leur catégorie ;
2. cache : téléchargé une fois depuis le 01/01/2017, jamais la barre du jour en cours, jamais
   retéléchargé sans --rafraichir ; l'empreinte change si une barre change ;
3. contrôles : lignes sans prix retirées ; date en double, prix nul ou négatif, trou de plus de
   5 jours de bourse, trop peu de barres : titre écarté et nommé ; un week-end n'est pas un trou ;
4. script : rapport des contrôles, code de sortie.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_donnees -v
Source simulée, barres inventées, dossier temporaire ; aucun réseau, aucun .env, rien dans data/.
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import pandas as pd

from rejeu import donnees
from rejeu import parametres as P
from scripts import rejeu_donnees
from tests.rejeu_fixtures import barres, jours_ouvres, source

AUJOURD_HUI = date(2018, 6, 1)
JOURS = jours_ouvres(date(2017, 1, 2), 300)


def serie(n=300, debut=100.0):
    return barres(JOURS[:n], [debut + i * 0.1 for i in range(n)])


class BaseDonnees(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dossier = tmp.name
        piege = mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))
        piege.start()
        self.addCleanup(piege.stop)


class TestUnivers(unittest.TestCase):
    def test_titres_de_la_liste_suivie_par_git(self):
        u = donnees.univers()
        self.assertEqual(len(u), 23)
        self.assertEqual((u["BTC-USD"], u["AAPL"], u["SPY"], u["CL=F"]), ("crypto", "stocks", "etf", "cfd"))
        self.assertTrue(P.UNIVERS.endswith(os.path.join("data", "watchlist.json.exemple")))


class TestCache(BaseDonnees):
    def test_telecharge_une_fois_sans_la_barre_du_jour(self):
        jours = JOURS + [AUJOURD_HUI]
        src = source({"AAPL": barres(jours, [100.0 + i for i in range(len(jours))])})
        self.assertEqual(donnees.preparer_cache(["AAPL"], src, AUJOURD_HUI, self.dossier), ["AAPL"])
        self.assertEqual(src.appels, [("AAPL", date(2017, 1, 1), date(2018, 5, 31))])
        lues, controles = donnees.charger(["AAPL"], self.dossier)
        self.assertEqual((len(lues["AAPL"]), lues["AAPL"].index[-1], controles["AAPL"].raisons), (300, JOURS[-1], []))
        self.assertEqual(list(lues["AAPL"].columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(lues["AAPL"]["Close"].iloc[0], 100.0)
        avant = donnees.empreinte(["AAPL"], self.dossier)
        self.assertEqual(donnees.preparer_cache(["AAPL"], src, AUJOURD_HUI, self.dossier), [])  # déjà en cache
        self.assertEqual((len(src.appels), donnees.empreinte(["AAPL"], self.dossier)), (1, avant))
        autre = source({"AAPL": barres(jours, [101.0 + i for i in range(len(jours))])})
        self.assertEqual(donnees.preparer_cache(["AAPL"], autre, AUJOURD_HUI, self.dossier, rafraichir=True), ["AAPL"])
        self.assertNotEqual(donnees.empreinte(["AAPL"], self.dossier), avant)
        self.assertTrue(os.path.isfile(os.path.join(self.dossier, "barres", "AAPL.csv")))


class TestControles(unittest.TestCase):
    def controle(self, df):
        return donnees.controler("AAPL", df)

    def test_serie_saine_et_lignes_sans_prix(self):
        df = serie()
        df.iloc[10, df.columns.get_loc("Close")] = float("nan")
        propres, c = self.controle(df)
        self.assertEqual((c.barres, c.sans_prix, c.doublons, c.prix_non_positifs, c.trous, c.utilisable),
                         (299, 1, 0, 0, [], True))
        self.assertEqual((c.premiere, c.derniere, len(propres)), (JOURS[0], JOURS[-1], 299))

    def test_titre_ecarte_et_raison_nommee(self):
        double = pd.concat([serie(), serie().iloc[[5]]])
        negatif = serie()
        negatif.iloc[20, negatif.columns.get_loc("Low")] = -37.63
        nul = serie()
        nul.iloc[20, nul.columns.get_loc("Open")] = 0.0
        troue = serie().drop(index=JOURS[100:106])  # 6 barres manquantes : 7 jours de bourse d'écart
        for df, attendu in [(double, "1 date(s) en double"), (negatif, "1 barre(s) à prix nul ou négatif"),
                            (nul, "1 barre(s) à prix nul ou négatif"),
                            (troue, "1 trou(s) de plus de 5 jours de bourse (le plus long : 7)"),
                            (serie(249), "249 barres, moins de 250")]:
            with self.subTest(attendu=attendu):
                _, c = self.controle(df)
                self.assertEqual((c.utilisable, c.raisons), (False, [attendu]))

    def test_cinq_jours_de_bourse_ne_sont_pas_un_trou(self):
        _, c = self.controle(serie().drop(index=JOURS[100:104]))  # 4 barres manquantes : écart de 5
        self.assertEqual((c.trous, c.utilisable), ([], True))
        self.assertEqual(donnees.jours_de_bourse(date(2026, 11, 6), date(2026, 11, 9)), 1)  # vendredi → lundi
        _, c = self.controle(serie().drop(index=JOURS[100:106]))
        self.assertEqual(c.trous, [(JOURS[99], JOURS[106], 7)])


class TestScript(BaseDonnees):
    def test_rapport_des_controles(self):
        court = barres(JOURS[:40], [10.0] * 40)
        src = source({t: serie() for t in donnees.univers() if t != "CL=F"} | {"VST": court})
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = rejeu_donnees.lancer(telecharger=src, dossier=self.dossier, aujourd_hui=AUJOURD_HUI)
        texte = sortie.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Titres de l'univers : 23 ; téléchargés à ce lancement : 23 ; utilisables : 21", texte)
        self.assertRegex(texte, r"VST +40 barres .*ÉCARTÉ : 40 barres, moins de 250")
        self.assertRegex(texte, r"CL=F +0 barres .*ÉCARTÉ : 0 barres, moins de 250")
        self.assertRegex(texte, r"AAPL +300 barres +2017-01-02 au 2018-02-23 .*utilisable")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rejeu_donnees.lancer(telecharger=source({}), dossier=self.dossier + "_vide",
                                                  aujourd_hui=AUJOURD_HUI), 1)


if __name__ == "__main__":
    unittest.main()
