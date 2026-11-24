"""
tests/test_rejeu_moteur.py — Moteur du rejeu (rejeu/moteur.py) sur des séries fabriquées, dont le
résultat se calcule à la main. Le signal technique est fabriqué ; tout le reste est le VRAI code
de l'agent : moteur de décision, Risk Manager (stop, objectif, taille), Budget Manager, porte
d'entrée, anti-boucle, réévaluation.

1. cycle complet : décision à la clôture de J, entrée à l'ouverture de J+1, sortie à l'objectif ;
   ordres, frais et valeur du compte calculés à la main, profils « Revolut » et « CFD » ;
2. stop et objectif le même jour : le stop ; le jour même de l'entrée ;
3. signal inverse : fermeture à l'ouverture suivante, puis ouverture dans l'autre sens ;
4. règles du code : confiance sous le seuil, 5 positions au plus, anti-boucle de 24 h ;
5. capital : 100 € (budget sous le minimum viable, aucun trade), 10 000 € (taille × 10).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_moteur -v
Base jetable dans un dossier temporaire ; aucun réseau, aucun .env, rien dans data/.
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from rejeu import moteur
from tests.rejeu_fixtures import analyses_de, bougies, jours_ouvres

J = jours_ouvres(date(2018, 1, 1), 8)  # lundi 1er janvier 2018, puis 2, 3, 4, 5, 8, 9, 10
PLAT = (100, 100.5, 99.5, 100)
ACHAT, VENTE = ("ACHAT", 9), ("VENTE", 9)


def a(jour: date, heure: int) -> datetime:
    return datetime(jour.year, jour.month, jour.day, heure, tzinfo=timezone.utc)


class BaseMoteur(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.base = os.path.join(tmp.name, "agent.db")

    def rejouer(self, lignes: list, signaux: dict, capital=1000, profil="revolut", ticker="AAPL"):
        df = bougies(J, lignes)
        res = moteur.simuler(capital, profil, {ticker: df}, {ticker: analyses_de(df, signaux)}, self.base)
        self.assertEqual(res.erreurs, [])  # l'agent n'a journalisé aucune erreur
        return res


class TestCycleComplet(BaseMoteur):
    LIGNES = [PLAT, (100, 101, 99, 100.5), (100.5, 107, 100, 106.5), (106.5, 107, 106, 106.5)]

    def test_entree_a_l_ouverture_suivante_sortie_a_l_objectif(self):
        res = self.rejouer(self.LIGNES, {J[0]: ACHAT})
        entree, sortie = res.ordres
        # 1 000 € : 500 € investissables, 10 % au plus par trade = 50 € ; ATR 2 → stop 100 − 3 = 97,
        # objectif 100 + 6 = 106 ; 50 € / 100 = 0,5 unité
        self.assertEqual((entree.ref, entree.ticker, entree.quand, entree.sens, entree.quantite, entree.prix,
                          entree.frais, entree.stop, entree.style),
                         ("pos1-entree", "AAPL", a(J[1], 8), "achat", 0.5, 100.0, (("commission", D("1")),), 97.0,
                          "normal"))
        self.assertEqual((sortie.ref, sortie.quand, sortie.sens, sortie.quantite, sortie.prix, sortie.statut),
                         ("pos1-sortie", a(J[2], 12), "vente", 0.5, 106.0, "CLOSED_TP"))
        # J0 : rien ; J1 : −1 € de frais, +0,25 € latent ; J2 : +3 € bruts, −2 € de frais
        self.assertEqual(res.valeurs, [(J[0], D("1000")), (J[1], D("999.25")), (J[2], D("1001")), (J[3], D("1001"))])
        self.assertEqual((res.decisions[("BUY", "normal")], res.decisions[("HOLD", "normal")], res.ouvertes_a_la_fin),
                         (1, 3, 0))

    def test_profil_cfd_ecart_et_financement(self):
        res = self.rejouer(self.LIGNES, {J[0]: ACHAT}, profil="cfd")
        entree, sortie = res.ordres
        self.assertEqual((entree.quantite, entree.prix, sortie.prix), (0.5, 100.0, 106.0))  # mêmes trades
        self.assertEqual(entree.frais, (("spread", D("0.05")),))  # 0,10 % de 50 €
        self.assertEqual(dict(sortie.frais), {"spread": D("0.053"), "financement": D("0.01")})  # une nuit
        self.assertEqual([v for _, v in res.valeurs], [D("1000"), D("1000.20"), D("1002.887"), D("1002.887")])

    def test_stop_et_objectif_le_meme_jour_le_stop_est_pris(self):
        res = self.rejouer([PLAT, (100, 107, 96, 100), PLAT], {J[0]: ACHAT})
        entree, sortie = res.ordres
        self.assertEqual((sortie.prix, sortie.statut, sortie.quand), (97.0, "CLOSED_SL", a(J[1], 12)))
        self.assertEqual(entree.quand, a(J[1], 8))  # entrée et stop le même jour
        self.assertEqual(res.valeurs[1], (J[1], D("996.5")))  # −1,5 € bruts, −2 € de frais

    def test_ouverture_sous_le_stop_execute_a_l_ouverture(self):
        res = self.rejouer([PLAT, (100, 101, 99, 100), (95, 96, 94, 95.5)], {J[0]: ACHAT})
        self.assertEqual((res.ordres[1].prix, res.ordres[1].statut), (95.0, "CLOSED_SL"))
        self.assertEqual(res.valeurs[2], (J[2], D("995.5")))  # (95 − 100) × 0,5 = −2,5 ; −2 € de frais


class TestReglesDuCode(BaseMoteur):
    def test_signal_inverse_fermeture_puis_ouverture_dans_l_autre_sens(self):
        res = self.rejouer([PLAT, (100, 101, 99, 100), (99, 99.5, 98.5, 99), (99, 99.5, 98.5, 99)],
                           {J[0]: ACHAT, J[1]: VENTE})
        achat, fermeture, vente = res.ordres
        self.assertEqual((fermeture.ref, fermeture.quand, fermeture.prix, fermeture.statut),
                         ("pos1-sortie", a(J[2], 8), 99.0, "CLOSED_REVERSAL"))
        self.assertEqual((vente.ref, vente.sens, vente.quand, vente.prix, vente.stop), ("pos2-entree", "vente", a(J[2], 8),
                                                                                       99.0, 102.0))
        self.assertAlmostEqual(vente.quantite, 50 / 99)
        self.assertEqual(res.ouvertes_a_la_fin, 1)
        self.assertEqual(res.valeurs[2], (J[2], D("996.5")))  # −0,5 brut, 3 ordres à 1 €, latent nul

    def test_confiance_sous_le_seuil_de_la_porte(self):
        res = self.rejouer([PLAT, PLAT, PLAT], {J[0]: ("ACHAT", 7)})
        self.assertEqual((res.ordres, res.decisions[("BUY", "normal")]), ([], 1))
        self.assertEqual(dict(res.refus), {"Confiance n/n < seuil n/n (normal)": 1})
        self.assertEqual({v for _, v in res.valeurs}, {D("1000")})

    def test_anti_boucle_de_24_heures(self):
        lignes = [PLAT, (100, 107, 99.5, 106.5), (106.5, 107, 106, 106.5), (106.5, 107, 106, 106.5),
                  (106.5, 107, 106, 106.5)]
        res = self.rejouer(lignes, {J[0]: ACHAT, J[1]: ACHAT, J[2]: ACHAT})
        self.assertEqual([(o.ref, o.quand) for o in res.ordres],
                         [("pos1-entree", a(J[1], 8)), ("pos1-sortie", a(J[1], 12)),  # objectif le jour de l'entrée
                          ("pos2-entree", a(J[3], 8))])  # refusée le 3 (moins de 24 h), ouverte le 4
        self.assertEqual(res.refus["anti_boucle"], 1)

    def test_cinq_positions_au_plus(self):
        tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "AMD"]
        barres = {t: bougies(J, [PLAT, PLAT, PLAT]) for t in tickers}
        analyses = {t: analyses_de(barres[t], {J[0]: ACHAT}) for t in tickers}
        res = moteur.simuler(1000, "revolut", barres, analyses, self.base)
        self.assertEqual((len(res.ordres), res.ouvertes_a_la_fin, res.erreurs), (5, 5, []))
        self.assertEqual(res.refus["Max positions atteint (n/n)"], 1)
        self.assertEqual({o.quantite for o in res.ordres}, {0.5})  # 50 € chacune : 250 € investis sur 500
        self.assertEqual(res.valeurs[-1], (J[2], D("995")))  # 5 ordres à 1 €

    def test_capital_de_100_et_de_10000_euros(self):
        petit = self.rejouer([PLAT, PLAT, PLAT], {J[0]: ACHAT}, capital=100)
        self.assertEqual((petit.ordres, dict(petit.refus)), ([], {"Budget alloué n€ < minimum viable n€": 1}))
        grand = self.rejouer([PLAT, PLAT, PLAT], {J[0]: ACHAT}, capital=10000)
        self.assertEqual((len(grand.ordres), grand.ordres[0].quantite, grand.ordres[0].stop), (1, 5.0, 97.0))
        self.assertEqual(grand.valeurs[-1], (J[2], D("9999")))


if __name__ == "__main__":
    unittest.main()
