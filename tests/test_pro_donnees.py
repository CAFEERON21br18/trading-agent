"""
tests/test_pro_donnees.py — Préparation des données des pages (dashboard/pro/donnees.py).

1. un compte, et un seul : charger() refuse l'absence de compte ; les chiffres d'un compte ne
   bougent pas quand l'autre compte reçoit des trades ;
2. trades clos, mesures, série cumulée, frais, dividendes et apports nets, en EUR et en USD ;
3. taux manquant : « taux indisponible » au lieu d'un chiffre, bloc par bloc et trade par trade ;
4. devise autre que l'euro et le dollar : « devise non convertie » ;
5. filtre de période du compte paper : « tout » ou depuis le correctif du prix d'entrée, dont la
   date porte sa référence au registre ;
6. module pur : ni Flask, ni module de l'agent chargé par l'import.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_donnees -v
Grand livre temporaire, données inventées ; aucun réseau, aucun .env, rien dans data/.
"""

import os
import subprocess
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.pro import donnees
from tests.pro_fixtures import BasePro, quand


class TestCompteReel(BasePro):
    def setUp(self):
        super().setUp()
        self.reel = self.compte_reel()
        self.taux()
        self.source = donnees.charger(self.conn, self.reel)

    def test_trades_clos_dans_les_deux_devises(self):
        usd = donnees.trades_clos(self.source, "USD").valeur
        self.assertEqual([(t.symbole, t.pnl_brut, t.couts, t.pnl_net, t.devise) for t in usd],
                         [("AAA", D("100"), D("2"), D("98"), "USD"), ("BBB", D("-20"), D("0.5"), D("-20.5"), "USD")])
        eur = donnees.trades_clos(self.source, "EUR").valeur
        self.assertEqual([(t.pnl_net, t.devise, t.prix_entree) for t in eur],
                         [(D("78.4"), "EUR", D("100")), (D("-16.4"), "EUR", D("50"))])  # prix : devise de cotation

    def test_mesures_frais_et_mouvements(self):
        m = donnees.tableau_mesures(self.source, "EUR").valeur
        net = m["résultat net"]
        self.assertEqual((net.valeur, net.n, net.decidable, net.raison), (62.0, 2, False, "2 trades sur 100 requis"))
        self.assertEqual(m["taux de réussite"].valeur, 0.5)
        self.assertEqual((m["espérance en R"].valeur, m["espérance en R"].n), (None, 0))  # aucun stop connu
        self.assertAlmostEqual(m["part des coûts"].valeur, 2.5 / 80)
        frais = donnees.total_frais(self.source, "EUR").valeur
        self.assertEqual((frais.total, frais.ordres, frais.ordres_avec_frais), (D("3.6"), 6, 4))
        self.assertEqual(donnees.total_frais(self.source, "USD").valeur.total, D("4.5"))
        self.assertEqual(donnees.dividendes(self.source, "EUR").valeur.valeur, 1.2)
        apports = donnees.apports_nets(self.source, "USD").valeur
        self.assertEqual((apports.valeur, apports.n), (1125.0, 2))

    def test_serie_cumulee_et_positions(self):
        self.assertEqual(donnees.serie_cumulee(self.source, "EUR").valeur,
                         [(date(2026, 11, 5), D("78.4")), (date(2026, 11, 6), D("62.0"))])
        ouvertes = donnees.positions_ouvertes(self.source)
        self.assertEqual([(p.symbole, p.quantite, p.prix_entree, p.devise, p.couts) for p in ouvertes],
                         [("CCC", D("2"), D("200"), "USD", D("2")), ("DDD.PA", D("5"), D("20"), "EUR", D("0"))])

    def test_les_comptes_ne_s_additionnent_jamais(self):
        avant = donnees.tableau_mesures(self.source, "USD").valeur["résultat net"].valeur
        paper = self.compte_paper()
        apres = donnees.charger(self.conn, self.reel)
        self.assertEqual(donnees.tableau_mesures(apres, "USD").valeur["résultat net"].valeur, avant)
        self.assertEqual(len(apres.executions), 6)
        self.assertEqual({e.compte_id for e in donnees.charger(self.conn, paper).executions}, {paper})
        for absent in (None, 0, 99):
            with self.subTest(compte=absent), self.assertRaisesRegex(ValueError, "un compte, et un seul"):
                donnees.charger(self.conn, absent)

    def test_devise_d_affichage_inconnue_refusee(self):
        for bloc in (donnees.trades_clos, donnees.tableau_mesures, donnees.dividendes, donnees.total_frais,
                     donnees.serie_cumulee, donnees.lignes_trades):
            with self.subTest(bloc=bloc.__name__), self.assertRaisesRegex(ValueError, "devise d'affichage"):
                bloc(self.source, "GBP")


class TestTauxManquant(BasePro):
    def test_taux_indisponible_au_lieu_d_un_chiffre(self):
        source = donnees.charger(self.conn, self.compte_reel())  # aucun taux dans le grand livre
        for bloc in (donnees.trades_clos, donnees.tableau_mesures, donnees.serie_cumulee, donnees.total_frais,
                     donnees.dividendes):
            with self.subTest(bloc=bloc.__name__):
                resultat = bloc(source, "EUR")
                self.assertEqual((resultat.valeur, resultat.indisponible), (None, "taux indisponible"))
        self.assertEqual(donnees.apports_nets(source, "USD").indisponible, "taux indisponible")
        # sans bascule à faire, les chiffres existent
        self.assertEqual(donnees.tableau_mesures(source, "USD").valeur["résultat net"].valeur, 77.5)
        self.assertEqual(donnees.apports_nets(source, "EUR").valeur.valeur, 900.0)

    def test_trade_par_trade(self):
        reel = self.compte_reel()
        self.taux(debut=date(2026, 11, 6), fin=date(2026, 11, 6))  # couvre la clôture de BBB, pas celle d'AAA
        lignes = donnees.lignes_trades(donnees.charger(self.conn, reel), "EUR")
        self.assertEqual([(t.symbole, None if c is None else c.pnl_net) for t, c in lignes],
                         [("AAA", None), ("BBB", D("-16.4"))])
        self.assertEqual(lignes[0][0].pnl_net, D("98"))  # le trade d'origine reste lisible, en dollars

    def test_devise_non_convertie(self):
        c = self.compte_reel()
        self.ordre(c, "HHH.L", "achat", "1", "10", quand(11, 2), devise="GBP", frais="1")
        self.ordre(c, "HHH.L", "vente", "1", "12", quand(11, 3), devise="GBP")
        self.mouvement(c, "depot", "50", quand(11, 3), devise="GBP")
        self.taux()
        source = donnees.charger(self.conn, c)
        for bloc in (donnees.trades_clos, donnees.total_frais, donnees.apports_nets):
            with self.subTest(bloc=bloc.__name__):
                self.assertEqual(bloc(source, "EUR").indisponible, "devise non convertie : GBP")
        self.assertEqual(donnees.dividendes(source, "EUR").valeur.valeur, 1.2)  # aucun dividende en livres
        self.assertEqual([c is None for _, c in donnees.lignes_trades(source, "EUR")], [True, False, False])


class TestPeriodePaper(BasePro):
    def setUp(self):
        super().setUp()
        self.source = donnees.charger(self.conn, self.compte_paper())
        self.taux()

    def test_tout_ou_depuis_le_correctif(self):
        tout = donnees.tableau_mesures(self.source, "USD", "tout").valeur
        self.assertEqual((tout["résultat net"].valeur, tout["résultat net"].n), (10.0, 2))
        self.assertEqual((tout["espérance en R"].valeur, tout["espérance en R"].n), (0.75, 2))
        apres = donnees.tableau_mesures(self.source, "USD", "correctif").valeur
        self.assertEqual((apres["résultat net"].valeur, apres["résultat net"].n), (20.0, 1))
        self.assertEqual(apres["espérance en R"].valeur, 2.0)
        self.assertEqual([t.symbole for t in donnees.trades_clos(self.source, "USD", "correctif").valeur], ["FFF"])
        self.assertEqual(donnees.serie_cumulee(self.source, "USD", "correctif").valeur, [(date(2026, 10, 28), D("20"))])
        self.assertEqual(donnees.total_frais(self.source, "USD", "correctif").valeur.ordres, 3)
        self.assertEqual([p.symbole for p in donnees.positions_ouvertes(self.source, "correctif")], ["GGG"])
        with self.assertRaisesRegex(ValueError, "période inconnue"):
            donnees.trades_clos(self.source, "USD", "hier")

    def test_date_du_correctif_et_sa_reference(self):
        self.assertEqual(donnees.CORRECTIF_PRIX_ENTREE, datetime(2026, 10, 21, 13, 31, 27, tzinfo=timezone.utc))
        self.assertEqual(donnees.PERIODES, {"tout": None, "correctif": donnees.CORRECTIF_PRIX_ENTREE})
        with open(os.path.join(RACINE, "dashboard", "pro", "donnees.py"), encoding="utf-8") as f:
            source = f.read()
        avant = source[:source.index("CORRECTIF_PRIX_ENTREE = ")]
        self.assertIn("docs/REGISTRE_CRITERES.md §9.4", avant[-700:])
        with open(os.path.join(RACINE, "docs", "REGISTRE_CRITERES.md"), encoding="utf-8") as f:
            registre = " ".join(f.read().split())
        self.assertIn("La date effective est l'`entry_date` de la première position paper", registre)


class TestModulePur(unittest.TestCase):
    def test_ni_flask_ni_agent(self):
        code = ("import sys; from dashboard.pro import donnees, latent, prix; "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in "
                "('flask', 'agents', 'alerts', 'config', 'utils', 'scripts', 'yfinance')))")
        sortie = subprocess.run([sys.executable, "-c", code], cwd=RACINE, capture_output=True, text=True, timeout=60)
        self.assertEqual((sortie.returncode, sortie.stdout.strip()), (0, "[]"), sortie.stderr)


if __name__ == "__main__":
    unittest.main()
