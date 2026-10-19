"""
tests/test_intuition_journal.py — enregistrer_decision_intuitive branchée à l'étape 4 du Decision Engine,
en journal SEULEMENT (agents/intuition.journaliser_intuition).

Preuve : sur des analyses synthétiques (override HOLD → BUY, override BUY → NO_TRADE, intuition qui
confirme, intuition neutre), decider() rend exactement le même résultat (action, style, taille,
confiance, score, raisonnement, tout le dict) journal désactivé, journal actif, et journal en échec
(écriture qui lève, fichier illisible). Le journal ne reçoit que les cycles (ni chat, ni conseiller
réel), une entrée par actif, jour et décision, au format que lit le vault (30-Intuitions).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_intuition_journal -v
Audit métacognitif et pipeline simulés (aucun LLM) ; intuition_log.md temporaire.
"""

import copy
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from agents import decision_engine, intuition
from agents.vault.notes_positions import entrees_intuition


def analyses(tech=("NEUTRE", 0), fond=("NEUTRE", 0), perf=None, patterns=(), surveiller=()):
    return {"technique": {"direction": tech[0], "confiance": tech[1], "prix": 100.0},
            "fondamental": {"direction": fond[0], "confiance": fond[1]},
            "sentiment": {"direction": "NEUTRE", "confiance": 0},
            "risque": {"valide": True, "direction": "NEUTRE", "confiance": 0},
            "memory": {"perf": perf, "patterns": list(patterns), "lecons": []},
            "context": {"actifs_a_surveiller": list(surveiller)}}


CAS = {  # ticker inventé -> analyses
    "AAA": analyses(perf={"trades": 3, "winrate_pct": 80.0}, patterns=["p"]),                # HOLD -> BUY
    "BBB": analyses(("BULLISH", 8), ("BULLISH", 8), perf={"trades": 4, "winrate_pct": 20.0}),  # BUY -> NO_TRADE
    "CCC": analyses(("BULLISH", 8), ("BULLISH", 7), patterns=["p"]),                         # confirme BUY
    "DDD": analyses(("BEARISH", 9), ("BEARISH", 6)),                                          # intuition neutre
}


class TestJournalSeulement(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        self.journal = os.path.join(self.d.name, "intuition_log.md")
        pile = ExitStack()
        self.addCleanup(pile.close)
        pile.enter_context(mock.patch.object(intuition, "INTUITION_LOG", self.journal))
        pile.enter_context(mock.patch("agents.decision_engine_meta.audit_metacognitif", return_value=""))
        pile.enter_context(mock.patch("agents.skills.pipeline_cache.executer_pipeline_cache",
                                      return_value={"executed": False, "raison": "simulé"}))
        pile.enter_context(mock.patch("agents.technical_skills.setup_quality.noter_setup",  # lit la base : simulé
                                      return_value={"grade": "B", "score": 5, "criteres": [], "budget_boost": 1.0}))

    def decisions(self, origine="cycle"):
        return {t: decision_engine.decider(t, copy.deepcopy(a), origine=origine) for t, a in CAS.items()}

    def lire(self):
        if not os.path.exists(self.journal):
            return ""
        with open(self.journal, encoding="utf-8") as f:
            return f.read()

    def test_decisions_identiques_journal_actif_coupe_ou_en_echec(self):
        with mock.patch.object(intuition, "journaliser_intuition", lambda *a, **k: None):
            sans = self.decisions()
        actif = self.decisions()
        self.assertTrue(self.lire())  # le journal a bien été écrit
        os.remove(self.journal)
        with mock.patch.object(intuition, "enregistrer_decision_intuitive", side_effect=OSError("disque plein")):
            echec_ecriture = self.decisions()
        with open(self.journal, "w", encoding="utf-8") as f:
            f.write("x")
        with mock.patch("builtins.open", side_effect=PermissionError("verrouillé")):
            echec_lecture = self.decisions()
        self.assertEqual((sans["AAA"]["decision"], sans["BBB"]["decision"], sans["CCC"]["decision"]),
                         ("BUY", "NO_TRADE", "BUY"))  # les cas couvrent bien override et confirmation
        for cas in (actif, echec_ecriture, echec_lecture):
            self.assertEqual(cas, sans)

    def test_entrees_du_journal(self):
        self.decisions()
        self.decisions()  # second passage du même jour : pas de doublon
        texte = self.lire()
        self.assertEqual(texte.count("(intuition)"), 3)  # AAA, BBB, CCC ; DDD : intuition neutre
        self.assertEqual(texte.count("- **Override**"), 2)
        modifiees = {(t, d) for _, _, t, d, _ in entrees_intuition(texte)}
        self.assertEqual(modifiees, {("AAA", "BUY"), ("BBB", "NO_TRADE")})  # ce que le vault reprend

    def test_hors_cycles_rien(self):
        for origine in ("chat", "conseiller"):
            with self.subTest(origine=origine):
                self.decisions(origine)
                self.assertEqual(self.lire(), "")


if __name__ == "__main__":
    unittest.main()
