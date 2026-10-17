"""
tests/test_rapport_annexes.py — TODO §17 : analyse pré-trade condensée dans le rapport quotidien, pour
les seuls BUY et SELL du cycle, en affichage seulement ; règle 4 du cadre du 17/10/2026 : une section
annexe en échec ou trop longue laisse la routine aller au bout, avec les mêmes décisions.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_rapport_annexes -v
Barres inventées dans une base temporaire ; LLM et réseau piégés (aucun appel) ; routine simulée.
"""

import contextlib
import glob
import importlib
import math
import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from agents import orchestrator as orch
from agents import rapport_annexes, rapport_pretrade
from utils import database

PIEGES = [mock.patch("utils.llm.ask_llm", side_effect=AssertionError("aucun LLM")),
          mock.patch("socket.socket.connect", side_effect=AssertionError("aucun réseau"))]


def decision(ticker, action, conf=7, signal=True):
    sig = {"prix_entree": 117.0, "stop_loss": 111.0, "target_1": 129.0, "rr_1": 2.0} if signal else None
    return {"ticker": ticker,
            "decision": {"ticker": ticker, "decision": action, "confidence": conf, "score_composite": 2.4,
                         "reasoning": f"Thèse inventée {ticker}", "style": "normal",
                         "convergences": [], "contradictions": []},
            "analyses": {"technique": {"direction": "ACHAT", "confiance": 6, "tendance": "Haussière", "prix": 117.0},
                         "risque": {"valide": bool(signal), "signal": sig}}}


class BaseBarres(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patchs = [mock.patch.object(database, "DB_PATH", os.path.join(self.dossier.name, "t.db"))] + PIEGES
        for p in self.patchs:
            p.start()
        database.initialiser_base()
        conn = database.get_connection()
        for tf, n, pas in (("1d", 400, 1), ("1wk", 120, 7)):
            for i in range(n):
                c = 100 + 10 * math.sin(i / 15) + i * 0.05  # cours inventés
                conn.execute("INSERT INTO prices (ticker, timeframe, timestamp, open, high, low, close, volume) "
                             "VALUES ('AAA', ?, ?, ?, ?, ?, ?, 1000)",
                             (tf, (date(2025, 1, 1) + timedelta(days=i * pas)).isoformat(), c, c + 1, c - 1, c))
        conn.commit()
        conn.close()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()
        self.dossier.cleanup()


class TestSectionPretrade(BaseBarres):
    def test_buy_et_sell_seulement(self):
        texte = rapport_pretrade.section_pretrade([decision("AAA", "BUY"), decision("BBB", "HOLD"),
                                                  decision("CCC", "SELL", conf=6, signal=False)])
        self.assertIn("### AAA — BUY (7/10) [normal]", texte)
        self.assertIn("- **1. Graphique** : Haussière (HH + HL) | markup", texte)
        self.assertIn("- **3. Catalyseurs** : non disponible", texte)
        self.assertIn("- **7. Risque** : entrée 117.00 | SL 111.00 | R:R 2.00", texte)
        self.assertIn("### CCC — SELL (6/10) [normal]\n- **1. Graphique** : non disponible", texte)  # pas de barres
        self.assertIn("- **7. Risque** : non disponible", texte)
        self.assertNotIn("BBB", texte)
        self.assertIn("Affichage seulement", texte)

    def test_aucun_buy_ni_sell(self):
        self.assertEqual(rapport_pretrade.section_pretrade([decision("BBB", "HOLD")]), "")

    def test_actif_en_erreur_les_autres_rendus(self):
        d = decision("AAA", "BUY")
        d["analyses"] = None  # structure cassée
        texte = rapport_pretrade.section_pretrade([d, decision("CCC", "SELL", signal=False)])
        self.assertIn("### AAA — non disponible", texte)
        self.assertIn("### CCC — SELL", texte)


class TestAnnexes(unittest.TestCase):
    def setUp(self):
        self.patchs = [mock.patch("agents.skills.pipeline_cache.section_rapport", return_value="\n## Pipeline\n"),
                       mock.patch.object(rapport_annexes, "section_registre", return_value="\n## Registre\n")]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchs):
            p.stop()

    def test_chaque_section_en_echec_ou_trop_longue(self):
        rapides = [(n, m, f, 0.2) for n, m, f, _ in rapport_annexes.SECTIONS]
        textes = {f: f"[{f}]" for _, _, f, _ in rapides}
        with mock.patch.object(rapport_annexes, "SECTIONS", rapides), contextlib.ExitStack() as pile:
            for _, m, f, _ in rapides:
                pile.enter_context(mock.patch(f"{m}.{f}", return_value=textes[f]))
            complet = rapport_annexes.annexes([decision("AAA", "BUY")], "quotidien")
            self.assertEqual(complet, "".join(textes.values()) + "\n## Pipeline\n\n## Registre\n")
            for _, m, f, _ in rapides:
                for effet in (RuntimeError("panne simulée"), lambda d: time.sleep(3)):
                    with self.subTest(section=f, effet=effet), mock.patch(f"{m}.{f}", side_effect=effet):
                        t0 = time.monotonic()
                        self.assertEqual(rapport_annexes.annexes([decision("AAA", "BUY")], "quotidien"),
                                         complet.replace(textes[f], ""))
                        self.assertLess(time.monotonic() - t0, 2.0)

    def test_affichage_seulement(self):
        """Seuls l'orchestrateur (rapport et email) et les tests importent ces sections."""
        lecteurs = set()
        for chemin in glob.glob(os.path.join(RACINE, "**", "*.py"), recursive=True):
            rel = os.path.relpath(chemin, RACINE).replace(os.sep, "/")
            if rel.startswith(("tests/", ".venv/")) or rel in ("agents/rapport_annexes.py", "agents/rapport_pretrade.py",
                                                               "agents/report_sections.py"):
                continue
            with open(chemin, encoding="utf-8", errors="replace") as f:
                if any(m in f.read() for m in ("rapport_annexes", "rapport_pretrade", "pretrade_analysis",
                                                 "chart_reading", "report_sections")):
                    lecteurs.add(rel)
        self.assertEqual(lecteurs, {"agents/orchestrator.py"})


class TestRoutine(BaseBarres):
    """generer_rapport_quotidien simulé de bout en bout : même résultat, section en panne ou non."""

    def lancer(self, *pannes):
        recu, sauve = [], []
        patchs = [mock.patch.object(orch, n, return_value=v) for n, v in (
            ("init_paper", None), ("ouvrir", None), ("monitorer_positions", {}), ("clore", None),
            ("enregistrer_decisions", None), ("recuperer_dominance_btc", 50.0), ("calculer_correlation", 0.3),
            ("recuperer_fear_greed_crypto", {"valeur": 55, "label": "Neutral"}), ("charger_watchlist", {}),
            ("tous_les_tickers", ["AAA", "BBB"]), ("preparer_observations", []), ("observer_jev", None),
            ("executer_fantome_jev", None), ("enregistrer_snapshot_quotidien", None), ("etat_portefeuille", {}),
            ("formater_section_portefeuille", "## Portefeuille simulé"), ("formater_decision", "décision"))]
        patchs += [mock.patch.object(orch, "analyser_actif_complet", side_effect=lambda t, sg: decision(t, "")["analyses"]),
                   mock.patch.object(orch, "decider", side_effect=lambda t, a: decision(t, "BUY" if t == "AAA" else "HOLD")["decision"]),
                   mock.patch.object(orch, "executer_ouvertures", side_effect=lambda d: recu.append(d) or
                                     {"ouvertes": [], "refusees": [], "bm_resume": None}),
                   mock.patch.object(orch, "sauvegarder_rapport", side_effect=lambda r, dossier: sauve.append(r)),
                   mock.patch("agents.orchestrator_llm.narratif_quotidien", return_value=""),
                   mock.patch("agents.skills.pipeline_cache.section_rapport", return_value=""),
                   mock.patch.object(rapport_annexes, "section_registre", return_value="\n## Registre simulé\n"),
                   mock.patch.object(rapport_annexes, "SECTIONS",
                                     [(n, m, f, 0.5) for n, m, f, _ in rapport_annexes.SECTIONS]), *pannes]
        for p in patchs:
            p.start()
        try:
            rapport, actifs, toutes = orch.generer_rapport_quotidien()
        finally:
            for p in reversed(patchs):
                p.stop()
        return {"rapport": rapport, "sauve": sauve, "actifs": [a["decision"] for a in actifs],
                "decisions": [d["decision"] for d in toutes], "recu": [[x["decision"] for x in r] for r in recu]}

    def test_meme_cycle_chaque_section_en_panne_ou_trop_longue(self):
        temoin = self.lancer()
        self.assertIn("### AAA — BUY (7/10)", temoin["rapport"])
        for _, m, f, _ in rapport_annexes.SECTIONS:
            texte = getattr(importlib.import_module(m), f)([decision("AAA", "BUY")]).replace("\n", "")
            self.assertTrue(texte)
            for panne in (RuntimeError("panne simulée"), lambda d: time.sleep(3)):
                with self.subTest(section=f, panne=panne):
                    r = self.lancer(mock.patch(f"{m}.{f}", side_effect=panne))
                    self.assertEqual((r["decisions"], r["actifs"], r["recu"]),
                                     (temoin["decisions"], temoin["actifs"], temoin["recu"]))
                    self.assertEqual(r["rapport"].replace("\n", ""), temoin["rapport"].replace("\n", "").replace(texte, ""))
                    self.assertIn("## Registre simulé", r["rapport"])
                    self.assertEqual(len(r["sauve"]), 1)


if __name__ == "__main__":
    unittest.main()
