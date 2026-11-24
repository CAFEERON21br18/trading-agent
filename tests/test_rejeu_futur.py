"""
tests/test_rejeu_futur.py — Aucune donnée postérieure à J n'influence la décision de J.

Le signal technique est ici celui des VRAIES fonctions de l'agent (rejeu/analyse.py), sur des
séries de prix aléatoires fabriquées.
1. l'analyse du jour J est la même, que la série s'arrête à J ou qu'elle continue avec un futur
   tout autre : ce test ÉCHOUE si une barre postérieure à J entre dans le calcul ;
2. témoin : une analyse qui verrait une barre de plus rend un autre résultat (le test 1 sait donc
   détecter une fuite) ;
3. moteur entier : avec un futur différent après J, les ordres et la valeur du compte jusqu'à J
   sont identiques, et l'ordre décidé à J part bien à l'ouverture de J+1 ;
4. l'analyse répartie sur plusieurs processus rend le même résultat qu'en un seul.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_futur -v
Séries inventées, base jetable temporaire ; aucun réseau, aucun .env, rien dans data/.
"""

import os
import sys
import tempfile
import unittest
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import numpy as np

from rejeu import analyse, moteur
from tests.rejeu_fixtures import analyses_de, barres, bougies, jours_ouvres

JOURS = jours_ouvres(date(2017, 1, 2), 290)  # jusqu'au 9 février 2018
J = date(2018, 1, 19)  # jour de la décision examinée


def serie(graine: int, n: int = 290):
    alea = np.random.default_rng(graine)
    clotures = list(100 * np.exp(np.cumsum(alea.normal(0.001, 0.02, n))))
    return barres(JOURS[:n], [float(c) for c in clotures], ecart=0.012)


def avec_un_autre_futur(df, apres: date):
    """Même série jusqu'à `apres` ; ensuite, des prix sans rapport (krach, puis envolée)."""
    autre = df.copy()
    futur = [i for i, j in enumerate(autre.index) if j > apres]
    for rang, i in enumerate(futur):
        facteur = 0.5 if rang < len(futur) // 2 else 3.0
        autre.iloc[i, :4] = autre.iloc[i, :4] * facteur
    return autre


class TestAnalyseSansFutur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = serie(7)
        cls.analyses = analyse.analyser_titre("AAPL", cls.df)

    def test_l_analyse_de_j_ignore_les_barres_d_apres(self):
        autre = analyse.analyser_titre("AAPL", avec_un_autre_futur(self.df, J))
        coupee = analyse.analyser_titre("AAPL", self.df.iloc[[i for i, j in enumerate(self.df.index) if j <= J]])
        jours = [j for j in self.analyses if j <= J]
        self.assertGreaterEqual(len(jours), 14)
        self.assertEqual(max(coupee), J)
        for jour in jours:
            with self.subTest(jour=jour):
                self.assertEqual(autre[jour], self.analyses[jour])   # futur différent : même analyse
                self.assertEqual(coupee[jour], self.analyses[jour])  # pas de futur du tout : même analyse
        apres = [j for j in self.analyses if j > J]
        self.assertTrue(any(autre[j] != self.analyses[j] for j in apres))  # après J, le futur compte bien

    def test_temoin_une_barre_de_trop_change_l_analyse(self):
        vue = analyse.vue_agent(self.df)
        rangs = [i for i, j in enumerate(self.df.index) if date(2018, 1, 8) <= j <= J]
        fuites = sum(analyse.analyser_jour("AAPL", vue.iloc[:i + 2]) != self.analyses[self.df.index[i]] for i in rangs)
        self.assertEqual(fuites, len(rangs))  # chaque jour, voir J+1 change le résultat : la fuite se verrait

    def test_forme_de_l_analyse_de_l_agent(self):
        a = self.analyses[J]
        self.assertEqual(set(a.technique), {"direction", "confiance", "prix", "tendance", "motifs", "detail"})
        self.assertEqual(a.technique["prix"], float(self.df.loc[J, "Close"]))
        self.assertIn(a.technique["direction"], ("ACHAT", "VENTE", "NEUTRE"))
        self.assertEqual(min(self.analyses), date(2018, 1, 1))  # 2017 n'est qu'un amorçage

    def test_plusieurs_processus_meme_resultat(self):
        court = {"AAPL": self.df.iloc[:270], "MSFT": serie(11, 270)}
        seul = analyse.analyser_univers(court, processus=1)
        self.assertEqual(analyse.analyser_univers(court, processus=2), seul)
        self.assertEqual(seul["AAPL"], {j: a for j, a in self.analyses.items() if j <= court["AAPL"].index[-1]})


class TestMoteurSansFutur(unittest.TestCase):
    def test_ordres_et_valeurs_jusqu_a_j_identiques(self):
        jours = jours_ouvres(date(2018, 1, 1), 8)
        plat = (100, 100.5, 99.5, 100)
        df = bougies(jours, [plat, plat, plat, (100, 101, 99, 100), (100, 100.5, 99.5, 100), plat, plat, plat])
        autre = bougies(jours, [plat, plat, plat, (100, 101, 99, 100), (60, 300, 20, 250), (250, 400, 5, 9),
                                (9, 12, 1, 2), (2, 3, 1, 2)])
        signaux = {jours[2]: ("ACHAT", 9)}  # décision à la clôture du 3 janvier
        j = jours[3]  # jour examiné : le 4 janvier, jour de l'entrée
        resultats = []
        for serie_, extra in ((df, {}), (autre, {jours[4]: ("VENTE", 9), jours[5]: ("ACHAT", 9)})):
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
                resultats.append(moteur.simuler(1000, "revolut", {"AAPL": serie_},
                                                {"AAPL": analyses_de(serie_, {**signaux, **extra})},
                                                os.path.join(d, "agent.db")))
        a, b = resultats
        jusqu_a = lambda res: ([o for o in res.ordres if o.quand.date() <= j], [v for v in res.valeurs if v[0] <= j])
        self.assertEqual(jusqu_a(a), jusqu_a(b))
        entree = a.ordres[0]
        self.assertEqual((entree.quand.date(), entree.prix), (jours[3], 100.0))  # décidé le 3, exécuté à l'ouverture du 4
        self.assertNotEqual(a.valeurs, b.valeurs)  # après J, les deux futurs divergent


if __name__ == "__main__":
    unittest.main()
