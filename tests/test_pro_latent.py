"""
tests/test_pro_latent.py — Dernier prix connu et résultat latent (dashboard/pro/prix.py, latent.py).

1. dernier prix : la barre la plus récente parmi 1 jour et « 4h » ; barre hebdomadaire et
   clôture vide ignorées ; base ou table absente : aucun prix ; base lue sans être modifiée ;
2. un prix de plus de 3 jours n'est plus utilisé ;
3. résultat latent : position longue et vente à découvert ; position sans prix marquée
   « prix indisponible » et exclue du total, jamais comptée à 0 ; aucun prix : total None ;
4. taux manquant pour la bascule : « taux indisponible », les lignes restent valorisées ;
5. filtre de période du compte paper.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_latent -v
Bases temporaires, cours inventés ; aucun réseau, aucun .env, rien dans data/.
"""

import os
import sqlite3
import sys
import unittest
from datetime import date
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from dashboard.pro import donnees, latent, prix
from tests.pro_fixtures import AUJOURD_HUI, BasePro, empreinte, quand


class TestDernierPrix(BasePro):
    def test_barre_la_plus_recente_et_base_inchangee(self):
        self.cours("AAA", 100.0, "2026-11-06 00:00:00")
        self.cours("AAA", 101.0, "2026-11-09 00:00:00")
        self.cours("AAA", 999.0, "2026-11-09 00:00:00", timeframe="1wk")  # hebdomadaire : ignorée
        self.cours("BTC-USD", 50000.0, "2026-11-09 00:00:00")
        self.cours("BTC-USD", 50500.5, "2026-11-10 06:00:00+00:00", timeframe="4h")
        self.cours("BBB", None, "2026-11-09 00:00:00")  # clôture vide
        self.cours("BBB", 20.0, "2026-11-03 00:00:00")
        avant = empreinte(self.base)
        trouves = prix.derniers_prix(self.base, ["AAA", "BTC-USD", "BBB", "ZZZ", "AAA"])
        self.assertEqual(trouves, {"AAA": prix.Prix(D("101.0"), date(2026, 11, 9)),
                                   "BTC-USD": prix.Prix(D("50500.5"), date(2026, 11, 10)),
                                   "BBB": prix.Prix(D("20.0"), date(2026, 11, 3))})
        self.assertEqual(empreinte(self.base), avant)

    def test_base_ou_table_absente(self):
        self.assertEqual(prix.derniers_prix(os.path.join(self.dossier.name, "absente.db"), ["AAA"]), {})
        self.assertFalse(os.path.exists(os.path.join(self.dossier.name, "absente.db")))
        vide = os.path.join(self.dossier.name, "vide.db")
        sqlite3.connect(vide).close()
        self.assertEqual(prix.derniers_prix(vide, ["AAA"]), {})

    def test_prix_de_plus_de_trois_jours_inutilisable(self):
        self.assertTrue(prix.utilisable(prix.Prix(D("1"), date(2026, 11, 7)), AUJOURD_HUI))   # 3 jours
        self.assertFalse(prix.utilisable(prix.Prix(D("1"), date(2026, 11, 6)), AUJOURD_HUI))  # 4 jours
        self.assertFalse(prix.utilisable(None, AUJOURD_HUI))


class TestResultatLatent(BasePro):
    def latent(self, compte_id, devise="EUR", jour=AUJOURD_HUI, periode="tout"):
        source = donnees.charger(self.conn, compte_id)
        symboles = [p.symbole for p in donnees.positions_ouvertes(source)]
        return latent.resultat_latent(source, devise, prix.derniers_prix(self.base, symboles), jour, periode)

    def test_position_sans_prix_exclue_jamais_comptee_a_zero(self):
        reel = self.compte_reel()
        self.taux()
        r = self.latent(reel)
        ccc, ddd = r.lignes
        self.assertEqual((ccc.position.symbole, ccc.prix.valeur, ccc.latent, ccc.indisponible),
                         ("CCC", D("210.0"), D("20.0"), ""))
        self.assertEqual((ddd.position.symbole, ddd.prix, ddd.latent, ddd.indisponible),
                         ("DDD.PA", None, None, "prix indisponible"))
        self.assertEqual((r.total, r.indisponible, r.valorisees, r.sans_prix), (D("16"), "", 1, 1))
        self.assertEqual(self.latent(reel, "USD").total, D("20"))

    def test_prix_trop_vieux_ou_absent_total_none(self):
        reel = self.compte_reel()
        self.taux()
        tard = self.latent(reel, jour=date(2026, 11, 13))  # le cours de CCC date du 09/11 : 4 jours
        self.assertEqual([l.indisponible for l in tard.lignes], ["prix indisponible"] * 2)
        self.assertEqual((tard.total, tard.indisponible, tard.valorisees), (None, "", 0))
        sans_position = self.latent(self.compte_paper(), periode="tout")
        self.assertEqual(sans_position.total, D("7.2"))  # (50 − 47) × 3 = 9 $, vente à découvert
        vide = self.latent(self.ledger_sans_position())
        self.assertEqual((vide.lignes, vide.total), ([], None))

    def ledger_sans_position(self) -> int:
        c = ledger.compte(self.conn, "Vide", "demo", "EUR")
        self.conn.commit()
        return c

    def test_taux_manquant_pour_la_bascule(self):
        reel = self.compte_reel()  # aucun taux
        r = self.latent(reel, "EUR")
        self.assertEqual((r.total, r.indisponible), (None, "taux indisponible"))
        self.assertEqual(r.lignes[0].latent, D("20.0"))  # la ligne reste valorisée, en dollars
        self.assertEqual(self.latent(reel, "USD").total, D("20"))  # aucune bascule à faire

    def test_devise_non_convertie_et_devise_d_affichage(self):
        reel = self.compte_reel()
        self.ordre(reel, "HHH.L", "achat", "1", "10", quand(11, 2), devise="GBP")
        self.conn.commit()
        self.cours("HHH.L", 12.0)
        self.taux()
        r = self.latent(reel)
        self.assertEqual((r.total, r.indisponible, r.valorisees), (None, "devise non convertie : GBP", 2))
        with self.assertRaisesRegex(ValueError, "devise d'affichage"):
            self.latent(reel, "GBP")

    def test_filtre_de_periode(self):
        paper = self.compte_paper()
        self.ordre(paper, "III", "achat", "1", "10", quand(10, 2))  # ouverte avant le correctif
        self.conn.commit()
        self.cours("III", 11.0)
        self.taux()
        self.assertEqual(self.latent(paper, "USD").total, D("10"))  # 9 + 1
        self.assertEqual(self.latent(paper, "USD", periode="correctif").total, D("9"))


if __name__ == "__main__":
    unittest.main()
