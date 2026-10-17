"""
tests/test_conseil_tronque.py — TODO §9 : un conseil réel enrichi par le LLM garde la justification des
règles quand le texte du LLM ne se termine pas par une ponctuation de fin de phrase (réponse coupée par
max_tokens), et le journalise. Ni max_tokens ni le nombre d'appels ne changent.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_conseil_tronque -v
LLM simulé (aucun appel réel), conseils et positions inventés (règle 9), sans base ni réseau.
"""

import os
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from agents import real_advisor

REGLE = "Justification des règles inventée."
INV, INV_E = {"asset": "AAA"}, {"pnl_pct": 4.0, "pnl_eur": 2.0}
PLAN = {"name": "Plan inventé", "plan_type": "custom"}


def enrichir(*textes) -> tuple[list[dict], mock.MagicMock]:
    conseils = [{"recommendation": "HOLD", "reasoning": REGLE} for _ in textes]
    with mock.patch("utils.llm.ask_llm", side_effect=[{"text": t, "source": "groq"} for t in textes]) as llm:
        real_advisor._enrichir_llm(conseils, INV, INV_E, PLAN)
    return conseils, llm


class TestPhraseComplete(unittest.TestCase):
    def test_fins_de_phrase(self):
        for t in ("Patience sur AAA.", "Gardez le cap !", "Faut-il renforcer ?", "À suivre…",
                  "Il faut « attendre ».", "Renforcez (sur correction).", "**Conserver.**", "Prudence.\r\n"):
            with self.subTest(texte=t):
                self.assertTrue(real_advisor.phrase_complete(t))

    def test_textes_coupes(self):
        for t in ("AAA reste dans la zone de", "Patience sur AAA pour", "Bonne dynamique 🚀", "", None):
            with self.subTest(texte=t):
                self.assertFalse(real_advisor.phrase_complete(t))


class TestEnrichissement(unittest.TestCase):
    def test_texte_coupe_justification_des_regles_gardee_et_journalisee(self):
        with self.assertLogs("agents.real_advisor", level="WARNING") as journal:
            conseils, _ = enrichir("AAA reste dans la zone de")
        self.assertEqual(conseils[0]["reasoning"], REGLE)
        self.assertIn("sans fin de phrase", journal.output[0])
        self.assertNotIn("zone de", journal.output[0])  # le texte lui-même n'est pas journalisé

    def test_texte_complet_utilise(self):
        conseils, _ = enrichir("Patience sur AAA, conforme au plan inventé.")
        self.assertEqual(conseils[0]["reasoning"], "Patience sur AAA, conforme au plan inventé.")

    def test_meme_nombre_d_appels_et_meme_max_tokens(self):
        conseils, llm = enrichir("Phrase complète.", "Phrase coupée", "Autre phrase complète !")
        self.assertEqual(llm.call_count, 3)
        self.assertEqual({c.kwargs["max_tokens"] for c in llm.call_args_list}, {200})
        self.assertEqual([c["reasoning"] for c in conseils], ["Phrase complète.", REGLE, "Autre phrase complète !"])

    def test_llm_sans_texte_regles_gardees(self):
        conseils = [{"recommendation": "HOLD", "reasoning": REGLE}]
        with mock.patch("utils.llm.ask_llm", return_value={"text": None, "error": "groq_ko"}):
            real_advisor._enrichir_llm(conseils, INV, INV_E, PLAN)
        self.assertEqual(conseils[0]["reasoning"], REGLE)


if __name__ == "__main__":
    unittest.main()
