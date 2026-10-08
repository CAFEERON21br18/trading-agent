"""
tests/test_jev_bilan.py — scripts/jev_bilan.py : lecture seule, verrou de lecture, calculs.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_jev_bilan -v
Base SQLite en mémoire, sans réseau.
"""

import io
import os
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")

from utils import jev_db
from scripts import jev_bilan, jev_bilan_calc as calc

DEBUT = date(2026, 10, 12)  # lundi


def base(observations: list[dict], prix: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for ddl in jev_db._DDL:
        conn.execute(ddl)
    conn.execute("CREATE TABLE prices (ticker TEXT, timeframe TEXT, timestamp TEXT, close REAL)")
    for o in observations:
        ligne = {"cycle": "quotidien", "statut": "ok", "questions_version": "v1", "modele": "jev-1.13.0",
                 "position_ouverte": 0, **o}
        cols = [c for c in jev_db.COLONNES if c in ligne]
        conn.execute(f"INSERT INTO jev_observations ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     [ligne[c] for c in cols])
    for (ticker, jour), close in prix.items():
        conn.execute("INSERT INTO prices VALUES (?, '1d', ?, ?)", (ticker, f"{jour} 00:00:00", close))
    return conn


def obs(ticker: str, jour: date, p_acheter: float, decision="HOLD", heure="07:31") -> dict:
    return {"ticker": ticker, "jour": jour.isoformat(), "horodatage": f"{jour}T{heure}:00+00:00",
            "prix": 100.0, "p_acheter": p_acheter, "decision_moteur": decision,
            "action_jev": "acheter" if p_acheter >= 0.6 else "ne_rien_faire",
            "regime_jev": "haussier", "regime_moteur": "haussier"}


class TestCalculs(unittest.TestCase):
    def test_premiere_du_jour_et_statut(self):
        lignes = [dict(obs("SPY", DEBUT, 0.9, heure="09:00"), id=2, statut="ok", questions_version="v1"),
                  dict(obs("SPY", DEBUT, 0.1, heure="07:31"), id=1, statut="ok", questions_version="v1"),
                  dict(obs("QQQ", DEBUT, 0.9), id=3, statut="erreur", questions_version="v1")]
        gardees = calc.premieres_du_jour(lignes, "v1")
        self.assertEqual([(g["ticker"], g["p_acheter"]) for g in gardees], [("SPY", 0.1)])

    def test_rendement_net_de_couts(self):
        jours = [DEBUT + timedelta(days=i) for i in range(6)]
        conn = base([], {("SPY", j.isoformat()): 100 + i for i, j in enumerate(jours)})
        self.assertAlmostEqual(calc.rendement(conn, "SPY", DEBUT.isoformat(), 100.0), 0.04 - 0.002)
        self.assertIsNone(calc.rendement(conn, "SPY", jours[3].isoformat(), 100.0))  # J+5 pas encore là

    def test_unites_groupe_semaine(self):
        o = [{"ticker": "SPY", "jour": "2026-10-12", "rendement": 0.02},
             {"ticker": "QQQ", "jour": "2026-10-14", "rendement": 0.04},   # même groupe, même semaine
             {"ticker": "SPY", "jour": "2026-10-19", "rendement": 0.01},   # semaine suivante
             {"ticker": "AAPL", "jour": "2026-10-12", "rendement": 0.05}]  # actif seul
        u = calc.unites(o)
        self.assertEqual(len(u), 3)
        self.assertAlmostEqual(u[("INDICES_US", "2026-S42")], 0.03)

    def test_classes_hors_positions(self):
        o = [dict(obs("SPY", DEBUT, 0.7), position_ouverte=1), obs("QQQ", DEBUT, 0.7, "BUY"), obs("VOO", DEBUT, 0.2)]
        cl = calc.classes(o)
        self.assertEqual([x["ticker"] for x in cl["jev_acheter"]], ["QQQ"])
        self.assertEqual([x["ticker"] for x in cl["moteur_buy"]], ["QQQ"])
        self.assertEqual([x["ticker"] for x in cl["jev_ne_rien_faire"]], ["VOO"])

    def test_bootstrap_par_grappes_de_semaines(self):
        une_semaine = {("CRYPTO", "2026-S42"): 0.01, ("SPY", "2026-S42"): 0.03}
        self.assertEqual(calc.bootstrap_grappes(une_semaine)[1:], (None, None))  # 1 grappe : pas d'IC
        u = {(g, f"2026-S{s}"): 0.01 * s for g in ("CRYPTO", "AAPL") for s in (42, 43, 44)}
        m, bas, haut = calc.bootstrap_grappes(u)
        self.assertAlmostEqual(m, 0.43)
        self.assertTrue(0.42 <= bas <= m <= haut <= 0.44)
        self.assertEqual(calc.bootstrap_grappes(u), calc.bootstrap_grappes(u))  # graine fixe
        b = {k: v - 0.01 for k, v in u.items()}
        ecart, bas, haut = calc.bootstrap_grappes_difference(u, b)
        self.assertAlmostEqual(ecart, 0.01)
        self.assertAlmostEqual(bas, 0.01)  # semaines appariées : l'écart est constant
        self.assertAlmostEqual(haut, 0.01)

    def test_couts_par_groupe(self):
        self.assertEqual([calc.cout(t) for t in ("SOL-USD", "QQQ", "AMD", "GC=F")],
                         [0.010, 0.002, 0.002, 0.002])

    def test_controle_regime_dix_jours_de_bourse(self):
        jours = [DEBUT + timedelta(days=i) for i in range(14)]  # 10 jours ouvrés + 2 week-ends
        bons = [obs("SPY", j, 0.5) for j in jours]
        self.assertEqual(calc.controle_regime(bons[:9])["statut"], "en_cours")
        self.assertEqual(calc.controle_regime(bons)["statut"], "ok")
        mauvais = [dict(o, regime_jev="range") for o in bons]
        ctrl = calc.controle_regime(mauvais)
        self.assertEqual((ctrl["statut"], ctrl["jusqu_au"]), ("arret", jours[11].isoformat()))

    def test_verdict_non_concluant_sous_le_minimum(self):
        self.assertTrue(jev_bilan.verdict(10, (0.05, 0.03, 0.07), (0.05, 0.02, 0.08), 0.1)
                        .startswith("NON CONCLUANT"))
        self.assertTrue(jev_bilan.verdict(50, (0.05, 0.03, 0.07), (0.05, 0.02, 0.08), 0.9).startswith("REDONDANT"))
        self.assertTrue(jev_bilan.verdict(50, (0.05, -0.01, 0.07), (0.05, 0.02, 0.08), 0.1).startswith("NON ATTEINT"))


class TestVerrouDeLecture(unittest.TestCase):
    def _sortie(self, aujourd_hui: date) -> str:
        observations = [obs("SPY", DEBUT + timedelta(days=7 * s), 0.8) for s in range(12)]
        prix = {("SPY", (DEBUT + timedelta(days=i)).isoformat()): 100 + i * 0.1 for i in range(100)}
        tampon = io.StringIO()
        with redirect_stdout(tampon):
            jev_bilan.main(aujourd_hui=aujourd_hui, conn=base(observations, prix))
        return tampon.getvalue()

    def test_avant_lecture_seulement_des_compteurs(self):
        sortie = self._sortie(DEBUT + timedelta(weeks=12, days=9))
        self.assertIn("Aucun résultat avant la date de lecture", sortie)
        self.assertIn("Unités indépendantes Jev-acheter", sortie)
        self.assertNotIn("moyenne", sortie)
        self.assertNotIn("%", sortie.split("Contrôle de lecture")[0])

    def test_a_la_lecture_resultats_et_verdict(self):
        sortie = self._sortie(DEBUT + timedelta(weeks=12, days=10))
        self.assertIn("VERDICT : NON CONCLUANT", sortie)  # 12 unités < 40
        self.assertIn("descriptif, pas un critère", sortie)

    def test_base_absente_ou_table_absente(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.assertEqual(jev_db.lire(conn), [])


if __name__ == "__main__":
    unittest.main()
