"""
tests/test_pro_latent.py — Dernier prix connu et résultat latent (dashboard/pro/prix.py, latent.py).

1. dernier prix : la barre la plus récente parmi 1 jour et « 4h » ; barre hebdomadaire et
   clôture vide ignorées ; base ou table absente : aucun prix ; base lue sans être modifiée ;
2. un prix de plus de 3 jours de bourse n'est plus utilisé : celui du vendredi vaut le lundi ;
   le cours du grand livre passe avant celui de la base de l'agent, lu seulement s'il manque ;
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

    def test_age_en_jours_de_bourse(self):
        vendredi, lundi = date(2026, 11, 6), date(2026, 11, 9)
        # samedi, dimanche, lundi, mercredi, jeudi qui suivent ce vendredi
        self.assertEqual([prix.jours_de_bourse(vendredi, date(2026, 11, j)) for j in (7, 8, 9, 11, 12)],
                         [0, 0, 1, 3, 4])
        cours_du_vendredi = prix.Prix(D("1"), vendredi)
        self.assertTrue(prix.utilisable(cours_du_vendredi, lundi))  # le cours du vendredi vaut le lundi
        self.assertTrue(prix.utilisable(cours_du_vendredi, date(2026, 11, 11)))   # mercredi : 3 jours de bourse
        self.assertFalse(prix.utilisable(cours_du_vendredi, date(2026, 11, 12)))  # jeudi : 4
        self.assertTrue(prix.utilisable(prix.Prix(D("1"), date(2026, 11, 8)), AUJOURD_HUI))  # dimanche, lu le mardi
        self.assertFalse(prix.utilisable(None, AUJOURD_HUI))


class TestGrandLivreDAbord(BasePro):
    def latent(self, compte_id, devise="EUR"):
        source = donnees.charger(self.conn, compte_id)
        symboles = [p.symbole for p in donnees.positions_ouvertes(source)]
        return latent.resultat_latent(source, devise, prix.prix_connus(self.conn, self.base, symboles), AUJOURD_HUI)

    def test_cours_du_grand_livre_puis_base_de_l_agent_s_il_manque(self):
        self.cours("CCC", 210.0)
        self.cours("DDD.PA", 21.0)
        self.cours_livre("CCC", "211", jour=date(2026, 11, 6))
        self.cours_livre("CCC", "212")
        connus = prix.prix_connus(self.conn, self.base, ["CCC", "DDD.PA", "ZZZ", "CCC"])
        self.assertEqual(connus, {"CCC": prix.Prix(D("212"), date(2026, 11, 9), "grand livre", "USD"),
                                  "DDD.PA": prix.Prix(D("21.0"), date(2026, 11, 9), "base de l'agent", None)})
        self.assertEqual(prix.prix_connus(None, self.base, ["CCC"])["CCC"].valeur, D("210.0"))  # sans grand livre

    def test_resultat_latent_au_cours_du_grand_livre(self):
        reel = self.compte_reel()  # la base de l'agent donne 210 pour CCC
        self.taux()
        self.cours_livre("CCC", "212")
        self.cours_livre("DDD.PA", "21", jour=date(2026, 11, 6), devise="EUR")
        r = self.latent(reel)
        self.assertEqual([(l.position.symbole, l.prix.valeur, l.prix.origine, l.latent) for l in r.lignes],
                         [("CCC", D("212"), "grand livre", D("24")), ("DDD.PA", D("21"), "grand livre", D("5"))])
        self.assertEqual((r.total, r.jours_des_cours), (D("24.2"), (date(2026, 11, 6), date(2026, 11, 9))))

    def test_cours_du_grand_livre_trop_vieux_ou_dans_une_autre_devise(self):
        reel = self.compte_reel()  # base de l'agent : CCC à 210, du 09/11
        self.taux()
        self.cours_livre("CCC", "190", jour=date(2026, 11, 2))  # 6 jours de bourse avant le 10/11
        r = self.latent(reel)
        self.assertEqual([l.indisponible for l in r.lignes], ["prix indisponible"] * 2)  # pas de repli sur 210
        self.assertEqual((r.total, r.jours_des_cours), (None, None))
        self.cours_livre("CCC", "195", devise="EUR")  # cours récent, mais pas dans la devise de la position
        self.assertEqual(self.latent(reel).lignes[0].indisponible, "prix indisponible")


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
