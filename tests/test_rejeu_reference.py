"""
tests/test_rejeu_reference.py — Référence « acheter et garder » et enveloppe du rejeu
(rejeu/reference.py, rejeu/enveloppe.py), sur des séries fabriquées.

1. référence annuelle : parts égales entre les titres présents en début d'année, achat à la
   première ouverture, vente à la dernière clôture, valeur réinvestie l'année suivante ; un titre
   coté en cours d'année attend l'année suivante ; chiffres calculés à la main ;
2. référence de période : une part par titre, investie à la première barre du titre, gardée
   jusqu'à la fin ; profil « CFD » : écart et financement ; part trop petite : espèces ;
3. enveloppe : pendant le rejeu, réseau, LLM et e-mail lèvent une erreur ; ensuite, la
   configuration et la base de l'agent sont remises en place ; rien n'est écrit hors du dossier.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_reference -v
Calcul sur des valeurs inventées ; base jetable temporaire ; aucun réseau, aucun .env.
"""

import logging
import os
import socket
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from rejeu import enveloppe, reference
from tests.rejeu_fixtures import bougies

J18 = [date(2018, 1, 2), date(2018, 6, 29), date(2018, 12, 31)]
J19 = [date(2019, 1, 2), date(2019, 12, 31)]


def b(o, c):
    return (o, max(o, c), min(o, c), c)


class TestReferences(unittest.TestCase):
    def setUp(self):
        # AAPL : 100 → 120 en 2018, puis 120 → 150 en 2019 ; MSFT : 50 → 40, puis 40 → 60
        # VRT n'est coté qu'à partir de juin 2018 : il attend 2019 pour la référence annuelle
        self.barres = {
            "AAPL": bougies(J18 + J19, [b(100, 101), b(110, 111), b(118, 120), b(120, 121), b(149, 150)]),
            "MSFT": bougies(J18 + J19, [b(50, 49), b(45, 44), b(41, 40), b(40, 41), b(59, 60)]),
            "VRT": bougies(J18[1:] + J19, [b(10, 10), b(10, 10), b(10, 10), b(20, 20)]),
        }

    def test_reference_annuelle_calculee_a_la_main(self):
        res = reference.annuelle(1000, "revolut", self.barres)
        # 2018 : 2 titres, 500 € chacun, 1 € de frais → 499 € investis. AAPL : 4,99 unités, MSFT : 9,98.
        # Vente : 4,99 × 120 − 1 = 597,80 ; 9,98 × 40 − 1 = 398,20 → 996,00 €.
        fin_2018 = dict(res.valeurs)[date(2018, 12, 31)]
        self.assertAlmostEqual(float(fin_2018), 996.0, places=9)
        # 2019 : 3 titres, 332 € chacun, 331 € investis. AAPL ×150/120, MSFT ×60/40, VRT ×20/10, −1 € chacun.
        attendu = 331 * 150 / 120 + 331 * 60 / 40 + 331 * 20 / 10 - 3
        self.assertAlmostEqual(float(res.valeurs[-1][1]), attendu, places=9)
        self.assertEqual([(o.ref, o.sens, o.prix) for o in res.ordres[:4]],
                         [("2018-AAPL-achat", "achat", 100), ("2018-MSFT-achat", "achat", 50),
                          ("2018-AAPL-vente", "vente", 120), ("2018-MSFT-vente", "vente", 40)])
        self.assertEqual(len(res.ordres), 4 + 6)
        # valeur à la clôture du premier jour
        self.assertAlmostEqual(float(dict(res.valeurs)[date(2018, 1, 2)]), 499 * 101 / 100 + 499 * 49 / 50, places=9)
        self.assertEqual((res.nature, res.compte), ("reference_annuelle", "Référence annuelle 1000 EUR revolut"))

    def test_reference_de_periode_un_titre_entre_a_sa_premiere_barre(self):
        res = reference.periode(900, "revolut", self.barres, fin=date(2019, 12, 31))
        # 300 € par titre, 299 € investis ; VRT entre le 29 juin 2018 à 10. Vente à la dernière clôture.
        attendu = 299 * 150 / 100 + 299 * 60 / 50 + 299 * 20 / 10 - 3
        self.assertAlmostEqual(float(res.valeurs[-1][1]), attendu, places=9)
        self.assertEqual([o.ref for o in res.ordres], ["periode-AAPL-achat", "periode-MSFT-achat", "periode-VRT-achat",
                                                       "periode-AAPL-vente", "periode-MSFT-vente", "periode-VRT-vente"])
        self.assertEqual(res.ordres[2].quand.date(), date(2018, 6, 29))
        # le 2 janvier 2018, la part de VRT est encore en espèces
        self.assertAlmostEqual(float(dict(res.valeurs)[date(2018, 1, 2)]), 299 * 1.01 + 299 * 0.98 + 300, places=9)

    def test_profil_cfd_et_part_trop_petite(self):
        seul = {"AAPL": self.barres["AAPL"]}
        res = reference.periode(1000, "cfd", seul, fin=date(2018, 12, 31))
        achat, vente = res.ordres
        investi = D(1000) / D("1.001")  # la part paie l'écart de 0,10 %
        self.assertAlmostEqual(achat.quantite, float(investi) / 100)
        nuits = (date(2018, 12, 31) - date(2018, 1, 2)).days
        self.assertEqual(dict(vente.frais)["financement"].quantize(D("0.0001")),
                         (D("0.0002") * investi * nuits).quantize(D("0.0001")))
        attendu = float(investi) * 1.2 * (1 - 0.001) - float(D("0.0002") * investi * nuits)
        self.assertAlmostEqual(float(res.valeurs[-1][1]), attendu, places=6)
        petit = reference.periode(1, "revolut", seul, fin=date(2018, 12, 31))  # 1 € ne paie pas 1 € de frais
        self.assertEqual((petit.ordres, {v for _, v in petit.valeurs}), ([], {D(1)}))


class TestEnveloppe(unittest.TestCase):
    def test_garde_fous_puis_remise_en_place(self):
        import config
        from utils import database, llm
        avant = (config.CAPITAL, config.MAX_POSITIONS_SIMULTANEES, config.CAPITAL_STOP_THRESHOLD, database.DB_PATH)
        production = [os.path.join(RACINE, "data", n) for n in ("database.db", "registre.db", "ledger.db")]
        etat = [os.path.exists(p) and os.path.getmtime(p) for p in production]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = os.path.join(d, "agent.db")
            with enveloppe.agent_enveloppe(enveloppe.Contexte({}), 10000, base):
                self.assertEqual((config.CAPITAL, config.CAPITAL_INVESTISSABLE, config.CAPITAL_STOP_THRESHOLD,
                                  config.MAX_POSITIONS_SIMULTANEES, database.DB_PATH), (10000.0, 5000.0, 7000.0, 5, base))
                def connexion():
                    prise = socket.socket()
                    try:
                        prise.connect(("127.0.0.1", 9))
                    finally:
                        prise.close()
                for interdit in (lambda: llm.ask_llm("bonjour"), connexion,
                                 lambda: __import__("smtplib").SMTP("localhost")):
                    with self.assertRaises(enveloppe.AppelInterdit):
                        interdit()
                from agents.paper_trader import executor
                self.assertFalse(executor.envoyer_email("sujet", "corps"))  # aucun e-mail ne part
                self.assertTrue(os.path.isfile(base))  # la base de l'agent est celle du dossier jetable
            self.assertEqual(sorted(os.listdir(d))[0], "agent.db")
        self.assertEqual((config.CAPITAL, config.MAX_POSITIONS_SIMULTANEES, config.CAPITAL_STOP_THRESHOLD,
                          database.DB_PATH), avant)
        self.assertEqual(logging.root.manager.disable, 0)
        self.assertEqual([os.path.exists(p) and os.path.getmtime(p) for p in production], etat)
        self.assertGreaterEqual(len(enveloppe.NEUTRALISEES), 9)


if __name__ == "__main__":
    unittest.main()
