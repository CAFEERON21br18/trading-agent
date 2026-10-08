"""
tests/test_verif_chiffres.py — Contrôle des chiffres de la réponse du chat (mode avertissement).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_verif_chiffres -v
Sans base ni .env (la migration est testée sur une base SQLite en mémoire).
"""

import json
import os
import sqlite3
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py (importé par _audit_record) exige ces variables

from agents.chat._verif_chiffres import extraire_nombres, partie_prompt, references_du_prompt, verifier
from agents.chat import _audit_record
from utils import message_audit_db
from scripts.rapport_verif_chiffres import extrait, statistiques

PROMPT = ("INTENTION DÉTECTÉE : general\n\n== PAPER PORTFOLIO ==\n"
          "Capital : 1000.00€ | Investi : 314.61€ | Cash : 685.39€\n"
          "Positions : 13/20 | P&L latent : +13.68€ sur les 13 positions (prix de 17h16)\n\n"
          "== QUESTION DE L'UTILISATEUR ==\n{question}\n\n"
          "Ta réponse (4-12 lignes, française, basée UNIQUEMENT sur les faits ci-dessus) :")


def lus(texte: str) -> list[tuple]:
    return [(n["brut"], n["valeur"], n["unite"]) for n in extraire_nombres(texte)]


class TestFormats(unittest.TestCase):
    def test_milliers_espace_virgule_decimale(self):
        for esp in (" ", " ", " "):
            self.assertEqual(lus(f"1{esp}234,56")[0][1:], (1234.56, None))

    def test_point_decimal(self):
        self.assertEqual(lus("1234.56"), [("1234.56", 1234.56, None)])

    def test_virgule_milliers_point_decimal(self):
        self.assertEqual(lus("1,234.56"), [("1,234.56", 1234.56, None)])

    def test_pourcentages_signes(self):
        self.assertEqual(lus("+12,3 % puis -0.5%"), [("+12,3 %", 12.3, "%"), ("-0.5%", -0.5, "%")])
        self.assertEqual(lus("−4,69 %"), [("−4,69 %", -4.69, "%")])

    def test_note_sur_10(self):
        self.assertEqual(lus("confiance 7/10"), [("7/10", 7.0, "/10")])

    def test_euros(self):
        self.assertEqual(lus("323.20€"), [("323.20€", 323.2, "€")])
        self.assertEqual(lus("13,68 euros"), [("13,68 euros", 13.68, "€")])

    def test_milliers_k(self):
        self.assertEqual(lus("12k"), [("12k", 12000.0, None)])
        self.assertEqual(lus("1,2k€"), [("1,2k€", 1200.0, "€")])

    def test_position(self):
        self.assertEqual([n["position"] for n in extraire_nombres("A 12 et B 345")], [2, 10])


class TestExclusions(unittest.TestCase):
    def test_dates(self):
        for t in ("le 08/10", "08/10/2026", "2026-10-08", "2026-10-08T06:31:14+00:00", "8 octobre", "le 10/10"):
            self.assertEqual(lus(t), [], t)

    def test_heures(self):
        for t in ("15h20", "17 h 16", "07:30", "à 15h"):
            self.assertEqual(lus(t), [], t)

    def test_annees_seules(self):
        self.assertEqual(lus("en 2026, cible 2100"), [])
        self.assertEqual(lus("2050 €"), [("2050 €", 2050.0, "€")])

    def test_numeros_de_liste(self):
        self.assertEqual(lus("1. Premier point\n  2) Second\n1.5 % de hausse"), [("1.5 %", 1.5, "%")])

    def test_tickers(self):
        self.assertEqual(lus("CL=F, BTC-USD, S&P 500, Nasdaq 100, 2330.TW"), [])

    def test_identifiants(self):
        self.assertEqual(lus("gpt-oss-120b, SIG-0001, EMA20, v5.4.0, le 3e trimestre"), [])

    def test_fraction_qui_n_est_ni_date_ni_note(self):
        self.assertEqual(lus("Positions : 13/20"), [("13", 13.0, None), ("20", 20.0, None)])

    def test_unite_collee_conservee(self):
        self.assertEqual(lus("0.123456u"), [("0.123456", 0.123456, None)])


class TestReferences(unittest.TestCase):
    def test_partie_prompt_sans_le_system(self):
        stocke = "[SYSTEM]\nRéponds en 4 à 12 lignes, règle 8.\n\n[PROMPT]\nCapital : 1000.00€"
        self.assertEqual(references_du_prompt(partie_prompt(stocke)), [1000.0])

    def test_question_comprise_consigne_exclue(self):
        refs = references_du_prompt(PROMPT.format(question="J'ai acheté à 245,50 €, et maintenant ?"))
        self.assertIn(245.5, refs)
        self.assertNotIn(4.0, refs)  # « Ta réponse (4-12 lignes…) » n'est pas une donnée
        self.assertEqual(sorted(refs), [13.0, 13.0, 13.68, 20.0, 245.5, 314.61, 685.39, 1000.0])

    def test_bloc_echanges_precedents_jamais_reference(self):
        prompt = PROMPT.replace("== QUESTION", "== ÉCHANGES PRÉCÉDENTS ==\nAgent : P&L de +87,40 €\n\n== QUESTION")
        refs = references_du_prompt(prompt.format(question="Et maintenant ?"))
        self.assertNotIn(87.4, refs)
        self.assertEqual(verifier("Le P&L était de +87,40 €.", refs)["non_soutenus"], ["+87,40 €"])


class TestVerifier(unittest.TestCase):
    def test_arrondi_soutenu(self):
        v = verifier("Hausse de 12,3 %.", [12.34])
        self.assertEqual((v["soutenus"], v["non_soutenus"], v["taux_non_soutenus"]), (1, [], 0.0))

    def test_chiffre_invente(self):
        v = verifier("Ton P&L latent est de +45,10 €.", [13.68, 1000.0])
        self.assertEqual((v["nb_chiffres"], v["non_soutenus"], v["taux_non_soutenus"]), (1, ["+45,10 €"], 1.0))

    def test_non_disponible_sans_chiffre(self):
        v = verifier("Le P&L latent est non disponible : aucun prix récent.", [13.68])
        self.assertEqual((v["nb_chiffres"], v["taux_non_soutenus"]), (0, None))

    def test_reponse_sans_aucun_chiffre(self):
        self.assertEqual(verifier("Rien à signaler.", []),
                         {"version": 1, "nb_chiffres": 0, "soutenus": 0, "non_soutenus": [],
                          "petits_entiers": 0, "taux_non_soutenus": None})

    def test_petits_entiers_comptes_a_part(self):
        v = verifier("2 positions sur 3 sont en gain, 0 en perte.", [])
        self.assertEqual((v["petits_entiers"], v["nb_chiffres"], v["non_soutenus"]), (3, 0, []))

    def test_tolerance_relative(self):
        self.assertEqual(verifier("100,4", [100.0])["soutenus"], 1)       # 0,4 ≤ 0,5 % de 100,4
        self.assertEqual(verifier("101", [100.0])["non_soutenus"], ["101"])

    def test_valeur_absolue(self):
        self.assertEqual(verifier("Recul de −4,69 % ; P&L +0,00 €.", [4.69, 0.0])["soutenus"], 2)

    def test_reponse_reelle_du_message_25(self):
        refs = references_du_prompt(PROMPT.format(question="Quelle est mon P&L latent"))
        v = verifier("Ton P&L latent s’élève à **+13,68 €** (calculé sur les 13 positions au cours "
                     "de 17 h 16).", refs)
        self.assertEqual((v["nb_chiffres"], v["non_soutenus"]), (2, []))


class TestBranchementAudit(unittest.TestCase):
    ENR = {"llm_utilise": "groq", "prompt_envoye": "[SYSTEM]\nx\n\n[PROMPT]\n" + PROMPT.format(question="?"),
           "reponse_brute": "Capital de 1000 € et 45 % de hausse."}

    def test_reponse_llm_verifiee(self):
        v = json.loads(_audit_record._verification_chiffres(dict(self.ENR)))
        self.assertEqual((v["nb_chiffres"], v["non_soutenus"]), (2, ["45 %"]))

    def test_rule_based_ou_sans_prompt_null(self):
        self.assertIsNone(_audit_record._verification_chiffres({**self.ENR, "llm_utilise": "rule_based"}))
        self.assertIsNone(_audit_record._verification_chiffres({**self.ENR, "prompt_envoye": None}))

    def test_exception_donne_null(self):
        with mock.patch.object(_audit_record, "verifier", side_effect=ValueError("panne")), \
                mock.patch.object(_audit_record, "logger"):
            self.assertIsNone(_audit_record._verification_chiffres(dict(self.ENR)))


class TestMigration(unittest.TestCase):
    def test_colonne_ajoutee_si_absente_et_idempotente(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE message_audit (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, "
                     "source TEXT NOT NULL)")  # table d'avant la colonne
        message_audit_db.initialiser_audit_db(conn)
        message_audit_db.initialiser_audit_db(conn)
        colonnes = [r[1] for r in conn.execute("PRAGMA table_info(message_audit)")]
        self.assertEqual(colonnes.count("verification_chiffres"), 1)
        self.assertIn("verification_chiffres", message_audit_db.COLONNES)

    def test_table_neuve(self):
        conn = sqlite3.connect(":memory:")
        message_audit_db.initialiser_audit_db(conn)
        colonnes = [r[1] for r in conn.execute("PRAGMA table_info(message_audit)")]
        self.assertEqual(colonnes[1:], list(message_audit_db.COLONNES))


class TestRapport(unittest.TestCase):
    def test_statistiques_taux_inconnu_jamais_compte_zero(self):
        s = statistiques([(1, "a", verifier("45 %", [])), (2, "b", verifier("Rien.", [])),
                          (3, "c", verifier("45 % et 12 €", [12.0]))])
        self.assertEqual((s["avec_chiffres"], s["taux_moyen"]), (2, 0.75))
        self.assertEqual(s["top"][0][:2], ("45 %", 2))

    def test_extrait_de_80_caracteres(self):
        texte = "x" * 100 + " 45 % " + "y" * 100
        e = extrait(texte, 101, 4)
        self.assertEqual(len(e), 80)
        self.assertIn("45 %", e)


if __name__ == "__main__":
    unittest.main()
