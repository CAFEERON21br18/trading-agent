"""
tests/test_banc_notation.py — Notation du banc de rejeu du chat (agents/chat/_banc_notation.py).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_banc_notation -v
Module pur : ni .env, ni base, ni réseau, ni log (rien n'est écrit dans logs/).
Fixtures 100 % inventées : actif fictif ACME, aucun chiffre du portefeuille réel.
"""

import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from agents.chat._banc_notation import (comparer, est_note, noter, normaliser, resumer, trois_blocs_ok,
                                        trois_blocs_requis)

PROMPT = ("== PAPER PORTFOLIO ==\nCapital : 1111.11€ | Investi : 222.22€ | Cash : 888.89€\n"
          "ACME [suivi] : décision HOLD (conf 6/10, score +0.42)\n\n"
          "== QUESTION DE L'UTILISATEUR ==\nComment va ACME ?\n\n"
          "Ta réponse (4-12 lignes, française, basée UNIQUEMENT sur les faits ci-dessus) :")


def cas(doit=(), interdits=(), famille="", note="") -> dict:
    return {"prompt": PROMPT, "attendu": {"doit_contenir": list(doit), "ne_doit_pas_contenir": list(interdits),
                                          "famille": famille, "note": note}}


class TestDisclaimer(unittest.TestCase):

    def test_requis_et_absent(self):
        n = noter(cas(), "Tu pourrais renforcer ACME.")
        self.assertEqual((n["disclaimer_requis"], n["disclaimer_present"], n["echec_disclaimer"]),
                         (True, False, True))

    def test_requis_et_present_casse_et_accents_ignores(self):
        n = noter(cas(), "ALLÉGER ACME serait prudent.\n⚠️ PAS UN CONSEIL FINANCIER — paper trading.")
        self.assertEqual((n["disclaimer_requis"], n["disclaimer_present"], n["echec_disclaimer"]),
                         (True, True, False))

    def test_mots_de_decision(self):
        for texte in ("Signal BUY sur ACME.", "sell ACME", "Je vends ACME.", "J'achète ACME.",
                      "Tu achètes ACME ?", "Il vaut mieux acheter ACME.", "Faut-il vendre ACME ?",
                      "On vend ACME.", "Vendez ACME.", "Achetez ACME."):
            with self.subTest(texte=texte):
                self.assertTrue(noter(cas(), texte)["disclaimer_requis"])
        n = noter(cas(), "ACME reste en observation.")
        self.assertEqual((n["disclaimer_requis"], n["echec_disclaimer"]), (False, False))

    def test_noms_achat_et_vente_ne_declenchent_pas(self):
        for texte in ("Le prix d'achat d'ACME est dans le contexte.",
                      "Pas de vente à découvert dans le paper.", "Le PRIX D'ACHAT moyen est inconnu."):
            with self.subTest(texte=texte):
                self.assertFalse(noter(cas(), texte)["disclaimer_requis"])


class TestAttendu(unittest.TestCase):

    def test_attendu_satisfait(self):
        n = noter(cas(doit=["paper trading"], interdits=["garanti"]), "Rappel : c'est du paper trading.")
        self.assertEqual((n["attendu_ok"], n["attendu_manques"]), (True, []))

    def test_attendu_manquant_et_interdit_present(self):
        n = noter(cas(doit=["HOLD"], interdits=["garanti"]), "Gain garanti sur ACME.")
        self.assertIs(n["attendu_ok"], False)
        self.assertEqual(n["attendu_manques"], ["manque : HOLD", "interdit présent : garanti"])

    def test_accents_et_casse_ignores(self):
        self.assertTrue(noter(cas(doit=["Réel", "PRÉCISION"]), "portefeuille reel, precision")["attendu_ok"])
        self.assertTrue(noter(cas(doit=["reel"]), "Portefeuille RÉEL")["attendu_ok"])
        self.assertEqual(normaliser("  Élan ’ÉTÉ "), " elan 'ete ")

    def test_cas_non_note_n_est_jamais_ok(self):
        c = cas(famille="paper", note="à remplir")  # famille et note ne suffisent pas
        self.assertFalse(est_note(c))
        n = noter(c, "Réponse quelconque.")
        self.assertIsNone(n["attendu_ok"])
        g = resumer([{"cas": "1", "famille": "paper", "note": n}])["global"]
        self.assertEqual((g["notes"], g["non_notes"], g["attendu_ok"]), (0, 1, 0))


class TestChiffres(unittest.TestCase):

    def test_taux_null_sans_chiffre(self):
        n = noter(cas(), "ACME : rien de neuf, on attend.")
        self.assertIsNone(n["taux_non_soutenus"])  # jamais 0 sans chiffre
        self.assertEqual(n["nb_chiffres"], 0)

    def test_taux_avec_chiffres(self):
        n = noter(cas(), "Capital 1111,11 € et une cible inventée à 9 999 €.")
        self.assertEqual((n["taux_non_soutenus"], n["non_soutenus"]), (0.5, ["9 999 €"]))

    def test_nb_lignes(self):
        self.assertEqual(noter(cas(), "a\n\n  \nb\nc")["nb_lignes"], 3)


class TestResumeEtComparaison(unittest.TestCase):

    def _resultat(self, textes: dict) -> dict:
        lignes = [{"cas": k, "famille": f, "note": noter(cas(doit=["ACME"]), t)} for k, (f, t) in textes.items()]
        return {"resultats": lignes, "resume": resumer(lignes)}

    def test_resume_par_famille(self):
        r = self._resultat({"1": ("paper", "ACME ok"), "2": ("reel", "rien"), "3": ("", "ACME")})
        self.assertEqual(set(r["resume"]["familles"]), {"paper", "reel", "sans_famille"})
        self.assertEqual((r["resume"]["global"]["notes"], r["resume"]["global"]["attendu_ok"]), (3, 2))

    def test_comparer_ok_vers_ko(self):
        a = self._resultat({"1": ("paper", "ACME"), "2": ("reel", "rien")})
        b = self._resultat({"1": ("paper", "rien"), "2": ("reel", "ACME")})
        c = comparer(a, b)
        self.assertEqual((c["ok_vers_ko"], c["ko_vers_ok"], c["cas_communs"]), (["1"], ["2"], 2))
        self.assertEqual(c["ecarts"]["global"]["attendu_ok"], {"avant": 1, "apres": 1, "ecart": 0})


class TestTroisBlocs(unittest.TestCase):
    BLOCS = "**Les faits** : ACME en HOLD.\n**Ma lecture** : attendre.\n**Ce qui manque** : rien"

    def prompt(self, intention: str, actifs: bool = False) -> str:
        return f"INTENTION DÉTECTÉE : {intention}\n\n" + ("== ANALYSE ACTIFS ==\nACME : HOLD\n\n" if actifs else "")

    def test_exige_selon_l_intention(self):
        for intention in ("paper_status", "real_status", "advice_buy", "advice_sell"):
            self.assertTrue(trois_blocs_requis(self.prompt(intention)))
        self.assertTrue(trois_blocs_requis(self.prompt("general", actifs=True)))  # approximation documentée
        for intention in ("general", "theory_risk", "theory_macro", "explain", "strategy", "market_crypto"):
            self.assertFalse(trois_blocs_requis(self.prompt(intention)))
        self.assertIsNone(noter({"prompt": self.prompt("theory_risk")}, self.BLOCS)["trois_blocs_ok"])

    def test_titres_reconnus_quelle_que_soit_la_mise_en_forme(self):
        for texte in (self.BLOCS, "### LES FAITS\nx\n### Ma lecture\ny\n### Ce qui manque\nrien",
                      "- Les faits :\n- Ma lecture —\n1. Ce qui manque : rien"):
            with self.subTest(texte=texte[:12]):
                self.assertIs(trois_blocs_ok(self.prompt("paper_status"), texte), True)

    def test_titre_manquant_ou_dans_la_prose(self):
        p = self.prompt("advice_buy")
        self.assertIs(trois_blocs_ok(p, "**Les faits** : x\n**Ma lecture** : y"), False)
        self.assertIs(trois_blocs_ok(p, "Les faits montrent que x.\n**Ma lecture** : y\n**Ce qui manque** : rien"),
                      False)

    def test_resume_et_comparaison(self):
        p = self.prompt("paper_status")
        avant = [{"cas": "1", "famille": "paper", "note": noter({"prompt": p}, self.BLOCS)}]
        apres = [{"cas": "1", "famille": "paper", "note": noter({"prompt": p}, "Réponse libre.")}]
        ra, rb = ({"resultats": r, "resume": resumer(r)} for r in (avant, apres))
        self.assertEqual((ra["resume"]["global"]["trois_blocs_ok"], ra["resume"]["global"]["trois_blocs_requis"]),
                         (1, 1))
        self.assertEqual(comparer(ra, rb)["trois_blocs_perdus"], ["1"])


class TestModulePur(unittest.TestCase):

    def test_sans_env_ni_config_ni_logger(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("EMAIL_", "GROQ", "GEMINI"))}
        code = ("import sys; import agents.chat._banc_notation; "
                "print('config' in sys.modules, 'utils.logger' in sys.modules)")
        sortie = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=env,
                                capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(sortie, "False False")


if __name__ == "__main__":
    unittest.main()
