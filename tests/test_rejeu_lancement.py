"""
tests/test_rejeu_lancement.py — Un lancement complet du rejeu, de bout en bout, sur des séries
fabriquées (rejeu/lancement.py, grand_livre.py, etude.py, rapport.py, scripts/rejeu.py).

1. les six configurations et leurs références sont écrites dans le grand livre du rejeu, par
   ledger/ecriture.py : 18 comptes, trades avec leurs frais, valeur quotidienne ; écriture seule ;
2. relu dans le grand livre : mesures de la configuration qui décide calculées à la main, mêmes
   trades d'un profil de frais à l'autre, aucun trade à 100 € ;
3. rapport : hypothèses de frais en tête, verdict et ses trois conditions, tableau par année,
   sensibilité, limites (biais de sélection), trades par année ;
4. relance : les sorties précédentes sont archivées, rien n'est effacé ni doublé ;
5. rien n'est écrit hors du dossier du rejeu : ni data/ledger.db, ni data/database.db.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rejeu_lancement -v
Dossiers temporaires, signaux fabriqués ; aucun réseau, aucun .env, rien dans data/.
"""

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

import ledger
from rejeu import etude, grand_livre, lancement
from rejeu import parametres as P
from scripts import rejeu as script
from tests.rejeu_fixtures import analyses_de, bougies, jours_ouvres

J = jours_ouvres(date(2018, 1, 1), 4)
PLAT = (100, 100.5, 99.5, 100)
PRODUCTION = [os.path.join(RACINE, "data", n) for n in ("ledger.db", "database.db", "registre.db")]


def etat_production():
    return [os.path.exists(p) and os.path.getmtime(p) for p in PRODUCTION]


class TestLancement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.dossier, cls.rapports = os.path.join(cls.tmp.name, "rejeu"), os.path.join(cls.tmp.name, "rapports")
        # AAPL : achat décidé le 1er janvier, entrée le 2 à 100, objectif 106 touché le 3 ; MSFT : rien
        cls.barres = {"AAPL": bougies(J, [PLAT, (100, 101, 99, 100.5), (100.5, 107, 100, 106.5), (106.5, 107, 106, 106.5)]),
                      "MSFT": bougies(J, [PLAT] * 4)}
        cls.analyses = {"AAPL": analyses_de(cls.barres["AAPL"], {J[0]: ("ACHAT", 9)}),
                        "MSFT": analyses_de(cls.barres["MSFT"], {})}
        cls.avant = etat_production()
        cls.resume = cls.lancer()

    @classmethod
    def lancer(cls):
        return lancement.lancer(cls.dossier, cls.rapports, processus=1, barres=cls.barres, analyses=cls.analyses)

    def lire(self):
        conn = ledger.ouvrir_lecture(grand_livre.chemin(self.dossier))
        self.addCleanup(conn.close)
        return conn

    def test_grand_livre_du_rejeu_ecrit_par_ledger(self):
        conn = self.lire()
        comptes = ledger.comptes(conn)
        self.assertEqual(len(comptes), 18)  # 6 configurations × (rejeu, référence annuelle, référence période)
        self.assertEqual({(c.type, c.devise) for c in comptes}, {("demo", "EUR")})
        self.assertIn("Rejeu 1000 EUR revolut", [c.nom for c in comptes])
        ids = grand_livre.comptes(conn)
        executions = ledger.executions_actives(conn, ids["Rejeu 1000 EUR revolut"])
        self.assertEqual([(e.symbole, e.sens, str(e.quantite), str(e.prix), str(e.couts), e.devise) for e in executions],
                         [("AAPL", "achat", "0.5", "100.0", "1", "EUR"), ("AAPL", "vente", "0.5", "106.0", "1", "EUR")])
        self.assertEqual((str(executions[0].stop_initial), executions[0].bras), ("97.0", "regles"))
        self.assertEqual({l[0] for l in conn.execute("SELECT DISTINCT source FROM trades")}, {"rejeu"})
        self.assertEqual(len(grand_livre.valeurs(conn, ids["Rejeu 1000 EUR revolut"])), 4)
        ecriture = sqlite3.connect(grand_livre.chemin(self.dossier))
        self.addCleanup(ecriture.close)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "ecriture seule"):
            ecriture.execute("UPDATE trades SET prix = '1'")
        self.assertEqual(etat_production(), self.avant)  # ni data/ledger.db ni la base de l'agent
        self.assertTrue(os.path.normcase(grand_livre.chemin(self.dossier)).startswith(os.path.normcase(self.tmp.name)))

    def test_mesures_relues_dans_le_grand_livre(self):
        conn = self.lire()
        self.assertEqual(etude.configurations(conn)[0], (1000, "revolut"))
        self.assertEqual(len(etude.configurations(conn)), 6)
        e = etude.etudier(conn, 1000, "revolut")
        p = e.periode
        self.assertEqual((e.decide, p.trades, p.resultat_brut, p.frais, p.resultat_net, p.esperance, p.valeur_fin),
                         (True, 1, 3.0, 2.0, 1.0, 1.0, 1001.0))
        self.assertEqual((e.verdict, [c.numero for c in e.conditions], e.ouvertes, e.sorties),
                         ("non décidable", [1, 2, 3], 0, {"CLOSED_TP": 1}))
        self.assertEqual([a.numero for a in e.annees], list(range(2018, 2026)))
        self.assertEqual((e.annees[0].strategie.trades, e.annees[1].strategie.trades, e.annees[0].partielle), (1, 0, False))
        cfd = etude.etudier(conn, 1000, "cfd")
        self.assertAlmostEqual(cfd.periode.resultat_net, 2.887)
        self.assertEqual((cfd.decide, cfd.periode.trades), (False, 1))
        self.assertEqual(etude.etudier(conn, 100, "revolut").periode.trades, 0)  # budget sous le minimum viable
        self.assertEqual(etude.etudier(conn, 10000, "revolut").periode.resultat_net, 28.0)  # 5 unités : 30 − 2
        self.assertEqual(set(e.courbes), {"strategie", "reference_annuelle", "reference_periode"})
        self.assertEqual(len(grand_livre.trades(conn, grand_livre.comptes(conn)["Référence annuelle 1000 EUR revolut"])), 2)

    def test_rapport_et_resume(self):
        with open(self.resume["rapport"], encoding="utf-8") as f:
            rapport = f.read()
        self.assertTrue(self.resume["rapport"].endswith(os.path.join("rapports", "RAPPORT.md")))
        for attendu in ("**HYPOTHÈSES**", "à confirmer contre la grille tarifaire", "## 1. Verdict",
                        "**Verdict : « non décidable ».**", "**1 trades clos**", "## 2. Année par année",
                        "| 2018 | 1 | +1,00 € | +1,00 € |", "| 2025 | 0 | — | — |",
                        "## 3. Sensibilité aux frais et au capital", "1 000 € · Revolut **(décide)**",
                        "10 000 € · CFD", "(indicatif)", "Les trades sont les mêmes d'un profil de frais à l'autre",
                        "## 4. Limites", "**Biais de sélection.**", "**Analystes neutralisés.**", "**Frais CFD supposés.**",
                        "**Barres quotidiennes seulement.**", "## 5. Nombre de trades clos par année", "CLOSED_TP : 1",
                        "rien ici n'est un conseil"):
            self.assertIn(attendu, rapport)
        self.assertEqual(rapport.count("\n1. **"), 1)
        self.assertEqual([rapport.count(f"\n{n}. **") for n in (1, 2, 3)], [1, 1, 1])  # les trois conditions, une à une
        with open(os.path.join(self.dossier, "lancement.json"), encoding="utf-8") as f:
            resume = json.load(f)
        self.assertEqual((resume["memes_trades_entre_profils"], len(resume["configurations"]), resume["titres"]),
                         (True, 6, ["AAPL", "MSFT"]))
        self.assertEqual([c["erreurs_agent"] for c in resume["configurations"]], [0] * 6)
        self.assertEqual(resume["configurations"][2]["refus"], {})  # 1 000 €, Revolut : rien de refusé
        self.assertGreaterEqual(len(resume["neutralisees"]), 9)

    def test_relance_archive_sans_rien_effacer(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            dossier, rapports = os.path.join(d, "rejeu"), os.path.join(d, "rapports")
            for _ in range(2):
                with mock.patch.object(lancement.grand_livre, "archiver", wraps=grand_livre.archiver) as archiver:
                    lancement.lancer(dossier, rapports, processus=1, barres=self.barres, analyses=self.analyses)
            self.assertEqual(archiver.call_count, 1)  # appelé à chaque lancement, avant toute simulation
            archives = sorted(os.listdir(os.path.join(dossier, "archives")))
            # le premier lancement est gardé : grand livre, résumé et bases jetables de l'agent
            self.assertEqual(sorted({a.split("_")[0] for a in archives}), ["agent", "lancement", "ledger"])
            self.assertEqual(len([a for a in archives if a.startswith("agent_") and a.endswith(".db")]), 6)
            self.assertEqual(len(os.listdir(os.path.join(rapports, "archives"))), 1)
            conn = ledger.ouvrir_lecture(grand_livre.chemin(dossier))
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM comptes").fetchone()[0], 18)  # neuf, pas doublé
            finally:
                conn.close()

    def test_script_affiche_le_verdict(self):
        sortie = io.StringIO()
        with mock.patch.object(P, "DOSSIER", self.dossier), \
                mock.patch.object(lancement, "lancer", return_value=self.resume) as lancer, \
                contextlib.redirect_stdout(sortie):
            code = script.lancer(processus=1)
        texte = sortie.getvalue()
        self.assertEqual((code, lancer.call_args.kwargs), (0, {"processus": 1}))
        self.assertIn("Verdict (1 000 €, Revolut, 2018–2025, 1 trades clos) : « non décidable »", texte)
        self.assertRegex(texte, r"1\. FAUSSE — espérance nette \+1,00 € par trade sur 1 trades")
        # console Windows : la sortie est passée en UTF-8, le signe « − » ne fait plus planter l'affichage
        flux = mock.Mock(spec=["reconfigure", "write", "flush"])
        with mock.patch.object(P, "DOSSIER", self.dossier), mock.patch.object(lancement, "lancer", return_value=self.resume),                 mock.patch.object(sys, "stdout", flux):
            script.lancer(processus=1)
        flux.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    unittest.main()
