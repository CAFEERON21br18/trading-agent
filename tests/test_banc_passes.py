"""
tests/test_banc_passes.py — --passes N et --tous du banc de rejeu : moyenne et écart par cas,
majorité stricte des passes, --comparer sur les moyennes, avertissements de composition,
compatibilité avec les fichiers d'une seule passe.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_banc_passes -v
Aucun appel réseau (ask_llm simulé) ; valeurs inventées.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables

from agents.chat._banc_resume import agreger, avertissements, comparer, resumer
from scripts import _banc_rejeu as br, rejouer_chat as rc
from scripts._banc_fichiers import journaux_detaches

OK = {"text": "ACME tient.\n⚠️ Pas un conseil financier — paper trading.", "source": "groq", "tentatives": []}
LIMITE = {"text": None, "source": None, "error": "groq_ko:rate_limit_groq, gemini réservé",
          "tentatives": [{"fournisseur": "groq", "type_erreur": "rate_limit_groq"}]}


def note(taux=None, lignes=3, attendu=None, blocs=None, echec=False) -> dict:
    return {"taux_non_soutenus": taux, "nb_lignes": lignes, "attendu_ok": attendu, "echec_disclaimer": echec,
            "disclaimer_requis": echec, "trois_blocs_requis": blocs is not None, "trois_blocs_ok": blocs}


def lignes(cas: str, notes: list, famille: str = "paper") -> list:
    return [{"cas": cas, "famille": famille, "passe": i + 1, "note": n} for i, n in enumerate(notes)]


class TestAgregation(unittest.TestCase):

    def test_moyenne_ecart_min_max_par_cas(self):
        s = agreger(lignes("1", [note(0.2), note(0.4), note(None)]))["1"]
        t = s["taux_non_soutenus"]
        self.assertEqual((s["passes"], t["moyenne"], t["n"], t["min"], t["max"]), (3, 0.3, 2, 0.2, 0.4))
        self.assertAlmostEqual(t["ecart_type"], 0.1414, places=4)
        self.assertIsNone(agreger(lignes("2", [note(None)]))["2"]["taux_non_soutenus"]["moyenne"])  # jamais 0

    def test_majorite_stricte_des_passes(self):
        for attendus, statut in (([True, False, True], True), ([True, False, False], False),
                                 ([True, False], False), ([True], True), ([None, None], None)):
            with self.subTest(attendus=attendus):
                self.assertIs(agreger(lignes("1", [note(attendu=a) for a in attendus]))["1"]["attendu_ok"], statut)

    def test_chaque_cas_pese_un(self):
        r = lignes("1", [note(0.6)] * 3) + lignes("2", [note(0.0)])
        self.assertEqual(resumer(r)["global"]["taux_non_soutenus_moyen"], 0.3)  # et non (3 × 0,6 + 0) / 4

    def test_une_passe_donne_les_chiffres_d_avant(self):
        anciennes = [{"cas": "1", "famille": "paper", "note": note(0.5, 4, True, True)},
                     {"cas": "2", "famille": "reel", "note": note(0.0, 2, False, None, echec=True)}]
        g = resumer(anciennes)["global"]
        self.assertEqual((g["cas"], g["notes"], g["attendu_ok"], g["taux_non_soutenus_moyen"], g["nb_lignes_moyen"],
                          g["echecs_disclaimer"], g["trois_blocs_ok"], g["trois_blocs_requis"]),
                         (2, 2, 1, 0.25, 3.0, 1, 1, 1))


class TestComparaison(unittest.TestCase):

    def test_moyennes_par_cas_et_ok_vers_ko_a_la_majorite(self):
        a = {"resultats": lignes("1", [note(0.2, attendu=True)] * 3) + lignes("2", [note(0.1, attendu=True)] * 3)}
        b = {"resultats": lignes("1", [note(0.0, attendu=True), note(0.0, attendu=False), note(0.1, attendu=True)])
             + lignes("2", [note(0.4, attendu=False)] * 2 + [note(None, attendu=True)])}
        c = comparer(a, b)
        self.assertEqual(c["ok_vers_ko"], ["2"])  # le cas 1 reste OK : 2 passes sur 3
        self.assertEqual(c["par_cas"]["1"]["apres"]["moyenne"], round(0.1 / 3, 4))
        self.assertEqual(c["taux_apparie"], {"cas": 2, "avant": 0.15, "apres": round((round(0.1 / 3, 4) + 0.4) / 2, 4)})
        self.assertEqual((c["passes"], c["seulement_a"], c["seulement_b"]), ({"a": [3], "b": [3]}, [], []))
        self.assertEqual(avertissements({"temperature": 0.6}, {"temperature": 0.6}, c), [])

    def test_avertissements_de_composition(self):
        a = {"mode": "rejouer", "temperature": 0.6, "envoyes": 6, "prevus": 6,
             "resultats": lignes("1", [note(0.1)] * 3) + lignes("2", [note(0.1)] * 3)}
        b = {"mode": "rejouer", "temperature": 0.3, "envoyes": 2, "prevus": 3, "arret": "rate_limit_groq",
             "resultats": lignes("1", [note(0.1)] * 2)}
        alertes = " | ".join(avertissements(a, b, comparer(a, b)))
        for attendu in ("cas différents", "nombres de passes différents", "passage B incomplet",
                        "températures différentes"):
            self.assertIn(attendu, alertes)


class TestRejouerPasses(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cas = self.dossier.name
        self.logs = journaux_detaches(self.cas)  # rien dans logs/ (production)
        self.logs.__enter__()
        for i in range(1, 13):
            with open(os.path.join(self.cas, f"{i}.json"), "w", encoding="utf-8") as f:
                json.dump({"origine": "audit", "prompt": f"Prompt inventé {i}", "attendu": {}}, f)

    def tearDown(self):
        self.logs.__exit__(None, None, None)
        self.dossier.cleanup()

    def lancer(self, reponses, **kw) -> tuple:
        appel, pause = mock.Mock(side_effect=reponses), mock.Mock()
        with redirect_stdout(io.StringIO()):
            res = br.rejouer(self.cas, appel=appel, pause=pause, confirmer=lambda q: True, **kw)
        return res, appel, pause

    def test_passe_par_passe_et_plafond_de_3(self):
        res, appel, pause = self.lancer([OK] * 6, n_max=2, passes=5)
        self.assertEqual((res["passes"], res["cas"], res["envoyes"], res["prevus"]), (3, 2, 6, 6))
        self.assertEqual([(r["cas"], r["passe"]) for r in res["resultats"]],
                         [("1", 1), ("2", 1), ("1", 2), ("2", 2), ("1", 3), ("2", 3)])
        self.assertEqual((appel.call_count, pause.call_count, res["resume"]["global"]["cas"]), (6, 5, 2))

    def test_tous_remplace_max(self):
        res, appel, _ = self.lancer([OK] * 12, tous=True)
        self.assertEqual((res["cas"], appel.call_count), (12, 12))  # --max vaut 10 par défaut

    def test_arret_garde_les_passes_terminees(self):
        res, _, _ = self.lancer([OK, OK, LIMITE], n_max=2, passes=3)
        self.assertEqual((res["arret"], res["envoyes"], res["prevus"]), ("rate_limit_groq", 3, 6))
        self.assertEqual(agreger(res["resultats"])["1"]["passes"], 1)

    def test_ligne_de_commande(self):
        for argv in (["--passes", "2"], ["--tous"], ["--noter", "--passes", "3"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                rc.main(argv)


if __name__ == "__main__":
    unittest.main()
