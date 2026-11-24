"""
tests/test_import_paper.py — Adaptateur paper du socle (importeurs/paper.py, importeurs/devises.py).

1. Devise de cotation : EUR pour les suffixes .PA .DE .AS .MI .MC .LS, USD sinon ; tickers dont la
   devise reste incertaine (indice hors États-Unis, paire non cotée en dollars, autre suffixe) ;
2. une position fermée donne deux exécutions, une position ouverte une seule ; compte « Paper agent »
   de type paper, stop initial et bras « regles » dans le contexte, aucun coût ;
3. relancer n'ajoute aucun doublon ; une position ouverte qui se ferme n'ajoute que sa sortie ;
4. positions « boucle » jamais importées ; position importée puis marquée : annulée par une ligne
   d'annulation, aucune ligne supprimée ; sans la colonne de marquage : erreur claire, rien d'importé ;
5. position illisible : rien n'est écrit, l'erreur nomme la position ; à blanc : rien n'est écrit ;
6. la base de l'agent n'est pas modifiée ; le portefeuille fantôme Jev n'est pas lu.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_import_paper -v
Base paper fabriquée dans un dossier temporaire (schéma du paper trader, mode WAL), positions
inventées ; aucun réseau, aucun .env, rien dans data/.
"""

import hashlib
import os
import sys
import unittest
from decimal import Decimal as D

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
import mesures
from importeurs import devises, paper
from tests.socle_paper_fixtures import BasePaperLedger, creer_base, executer, fermer, position


class TestDevise(unittest.TestCase):
    def test_devise_de_cotation(self):
        cas = {"AAPL": "USD", "BTC-USD": "USD", "GC=F": "USD", "SPY": "USD", "MC.PA": "EUR", "SAP.DE": "EUR",
               "ASML.AS": "EUR", "ENI.MI": "EUR", "SAN.MC": "EUR", "EDP.LS": "EUR", " mc.pa ": "EUR",
               "VOD.L": "USD", "^FCHI": "USD", "USDJPY=X": "USD"}  # trois derniers : USD par défaut
        for ticker, attendu in cas.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(devises.devise_cotation(ticker), attendu)

    def test_devise_incertaine(self):
        for ticker in ("VOD.L", "NESN.SW", "^FCHI", "^N225", "USDJPY=X", "EURGBP=X", "BTC-EUR", " vod.l "):
            with self.subTest(ticker=ticker):
                self.assertTrue(devises.devise_incertaine(ticker))
        for ticker in ("AAPL", "BTC-USD", "GC=F", "EURUSD=X", "^GSPC", "^RUT", "BRK-B", "MC.PA", "SAP.DE"):
            with self.subTest(ticker=ticker):
                self.assertFalse(devises.devise_incertaine(ticker))


class TestSynchronisation(BasePaperLedger):
    def trois_positions(self):
        """Longue fermée en dollars, courte fermée en euros, longue ouverte."""
        return (position(self.base, "AAA", "LONG", "CLOSED_TP", prix=100.0, sortie=110.0, quantite=2.0, stop=95.0),
                position(self.base, "BBB.PA", "SHORT", "CLOSED_SL", prix=50.0, sortie=45.0, quantite=3.0, stop=52.0),
                position(self.base, "CCC-USD", "LONG", "OPEN", prix=10.0, quantite=1.5, stop=9.0, type_actif="crypto"))

    def test_fermee_deux_executions_ouverte_une(self):
        a, b, c = self.trois_positions()
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual((r.positions, r.boucles, r.importes, r.deja_presents, r.annules, r.erreurs),
                         (3, 0, 5, 0, 0, []))
        compte = self.conn.execute("SELECT nom, type, devise FROM comptes").fetchall()
        self.assertEqual([tuple(l) for l in compte], [("Paper agent", "paper", "EUR")])
        refs = [l[0] for l in self.conn.execute("SELECT ref_source FROM trades WHERE source = 'paper_agent' ORDER BY id")]
        self.assertEqual(refs, [f"position-{a}-entree", f"position-{a}-sortie", f"position-{b}-entree",
                                f"position-{b}-sortie", f"position-{c}-entree"])
        ex = {(e.symbole, e.sens): e for e in ledger.executions_actives(self.conn)}
        entree = ex[("AAA", "achat")]
        self.assertEqual((entree.quantite, entree.prix, entree.devise, entree.stop_initial, entree.bras),
                         (D("2.0"), D("100.0"), "USD", D("95.0"), "regles"))
        self.assertEqual(entree.horodatage.isoformat(), "2030-01-02T10:00:00+00:00")
        sortie = ex[("AAA", "vente")]
        self.assertEqual((sortie.prix, sortie.stop_initial, sortie.bras), (D("110.0"), None, None))
        self.assertEqual(ex[("BBB.PA", "vente")].devise, "EUR")  # entrée d'une position courte
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM couts").fetchone()[0], 0)  # aucun frais
        self.assertTrue(all(e.couts == 0 for e in ex.values()))
        classes = dict(self.conn.execute("SELECT symbole, classe FROM instruments").fetchall())
        self.assertEqual(classes, {"AAA": "action", "BBB.PA": "action", "CCC-USD": "crypto"})

    def test_mesures_sur_les_positions_importees(self):
        self.trois_positions()
        paper.synchroniser(self.conn, self.base)
        clos, ouvertes = mesures.reconstruire(ledger.executions_actives(self.conn))
        vus = {t.symbole: (t.sens, t.devise, t.pnl_brut, t.couts, t.risque, t.bras) for t in clos}
        self.assertEqual(vus, {"AAA": ("long", "USD", D("20.00"), D("0"), D("10.00"), "regles"),
                               "BBB.PA": ("court", "EUR", D("15.00"), D("0"), D("6.00"), "regles")})
        self.assertEqual([(p.symbole, p.sens, p.quantite) for p in ouvertes], [("CCC-USD", "long", D("1.5"))])

    def test_relance_sans_doublon_puis_fermeture(self):
        _, _, c = self.trois_positions()
        paper.synchroniser(self.conn, self.base)
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual((r.importes, r.deja_presents, self.nb_trades()), (0, 5, 5))
        fermer(self.base, c, 12.0)
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual((r.importes, r.deja_presents, self.nb_trades()), (1, 5, 6))
        self.assertEqual(mesures.reconstruire(ledger.executions_actives(self.conn))[1], [])

    def test_boucles_jamais_importees(self):
        for _ in range(3):
            position(self.base, "DDD", prix=117.0, sortie=116.0, boucle=1)
        position(self.base, "AAA")
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual((r.positions, r.boucles, r.importes, r.annules), (1, 3, 2, 0))
        self.assertEqual({e.symbole for e in ledger.executions_actives(self.conn)}, {"AAA"})
        self.assertIsNone(self.conn.execute("SELECT 1 FROM instruments WHERE symbole = 'DDD'").fetchone())

    def test_position_importee_puis_marquee_boucle_est_annulee(self):
        a = position(self.base, "AAA")
        position(self.base, "EEE")
        paper.synchroniser(self.conn, self.base)
        executer(self.base, "UPDATE positions SET boucle = 1 WHERE id = ?", (a,))
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual((r.boucles, r.importes, r.deja_presents, r.annules), (1, 0, 2, 2))
        self.assertEqual({e.symbole for e in ledger.executions_actives(self.conn)}, {"EEE"})
        self.assertEqual(self.nb_trades(), 6)  # 4 lignes d'origine, toujours lisibles, + 2 annulations
        annulations = self.conn.execute(
            "SELECT o.ref_source FROM trades a JOIN trades o ON o.id = a.remplace_id"
            " WHERE a.statut = 'annulation' ORDER BY o.id").fetchall()
        self.assertEqual([l[0] for l in annulations], [f"position-{a}-entree", f"position-{a}-sortie"])
        r = paper.synchroniser(self.conn, self.base)  # relance : plus rien à annuler
        self.assertEqual((r.annules, r.importes, self.nb_trades()), (0, 0, 6))

    def test_colonne_boucle_absente_rien_n_est_importe(self):
        nue = os.path.join(self.dossier.name, "sans_marquage.db")
        creer_base(nue, boucle=False)
        executer(nue, "INSERT INTO positions (ticker, direction, entry_price, entry_date, quantity,"
                      " invested_amount, stop_loss, target_1) VALUES ('AAA', 'LONG', 100, ?, 1, 100, 95, 110)",
                 ("2030-01-02T10:00:00+00:00",))
        with self.assertRaisesRegex(paper.ColonneBoucleAbsente, "marquer_boucles"):
            paper.synchroniser(self.conn, nue)
        self.assertEqual(self.nb_trades(), 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM comptes").fetchone()[0], 0)
        with self.assertRaises(paper.SynchronisationImpossible):
            paper.synchroniser(self.conn, os.path.join(self.dossier.name, "absente.db"))

    def test_position_illisible_rien_n_est_ecrit(self):
        position(self.base, "AAA")
        mauvaise = position(self.base, "FFF", statut="CLOSED_SL")
        executer(self.base, "UPDATE positions SET exit_price = NULL WHERE id = ?", (mauvaise,))
        autre = position(self.base, "GGG", direction="NEUTRE")
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual([i for i, _ in r.erreurs], [mauvaise, autre])
        self.assertIn("prix de sortie", r.erreurs[0][1])
        self.assertIn("direction", r.erreurs[1][1])
        self.assertEqual((r.importes, self.nb_trades()), (0, 0))

    def test_a_blanc_rien_n_est_ecrit(self):
        self.trois_positions()
        r = paper.synchroniser(self.conn, self.base, appliquer=False)
        self.assertEqual((r.importes, self.nb_trades()), (5, 0))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM comptes").fetchone()[0], 0)

    def test_devises_incertaines_signalees(self):
        position(self.base, "^FCHI")
        position(self.base, "VOD.L")
        position(self.base, "AAA")
        position(self.base, "NESN.SW", boucle=1)  # boucle : non importée, donc non signalée
        r = paper.synchroniser(self.conn, self.base)
        self.assertEqual(r.devises_incertaines, ["VOD.L", "^FCHI"])
        self.assertEqual({e.devise for e in ledger.executions_actives(self.conn)}, {"USD"})

    def test_base_de_l_agent_intacte_et_fantome_jev_non_lu(self):
        self.trois_positions()
        executer(self.base, "CREATE TABLE jev_paper_positions (id INTEGER PRIMARY KEY, ticker TEXT)")
        executer(self.base, "INSERT INTO jev_paper_positions (ticker) VALUES ('JEVX')")
        with open(self.base, "rb") as f:
            avant = hashlib.sha256(f.read()).hexdigest()
        paper.synchroniser(self.conn, self.base)
        with open(self.base, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), avant)
        symboles = {l[0] for l in self.conn.execute("SELECT symbole FROM instruments")}
        self.assertEqual(symboles, {"AAA", "BBB.PA", "CCC-USD"})


if __name__ == "__main__":
    unittest.main()
