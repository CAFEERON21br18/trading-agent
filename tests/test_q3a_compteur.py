"""
tests/test_q3a_compteur.py — scripts/q3a_compteur.py (REGISTRE_CRITERES §3.a, v1.7) : définition du
couple examiné, replis Prudent à part, semaine ISO du jour de Lisbonne, lecture seule, sortie sans
aucun champ de rendement, de moyenne ni de verdict.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_q3a_compteur -v
Registre synthétique (vrai schéma, chaîne de hachage), valeurs inventées, sans réseau.
"""

import hashlib
import io
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from scripts import q3a_compteur as q
from utils.registre_schema import COLONNES, GENESE, SCHEMA, _canon, empreinte_ligne

# (horodatage UTC, ticker, décision, style, origine, statut du pipeline, autres champs du contenu)
LIGNES = [
    ("2026-10-07T10:00:00+00:00", "AAA", "BUY", "normal", "cycle", "execute", {}),
    ("2026-10-07T14:00:00+00:00", "AAA", "BUY", "normal", "cycle", "cache", {}),      # même couple
    ("2026-10-07T15:00:00+00:00", "AAA", "SELL", "normal", "cycle", "execute", {}),    # autre action
    ("2026-10-11T23:30:00+00:00", "BBB", "BUY", "normal", "cycle", "execute", {}),     # lundi 12/10 à Lisbonne
    ("2026-10-08T09:00:00+00:00", "CCC", "BUY", "normal", "cycle", "prudent", {}),     # repli seul
    ("2026-10-08T09:00:00+00:00", "DDD", "SELL", "normal", "cycle", "prudent", {}),
    ("2026-10-08T12:00:00+00:00", "DDD", "SELL", "normal", "cycle", "cache", {}),      # repli puis cache
    ("2026-10-08T09:00:00+00:00", "EEE", "BUY", "learning", "cycle", "execute", {}),   # exclues ensuite
    ("2026-10-08T09:00:00+00:00", "FFF", "HOLD", "normal", "cycle", "saute", {}),
    ("2026-10-08T09:00:00+00:00", "GGG", "BUY", "normal", "conseiller", "execute", {}),
    ("2026-10-08T09:00:00+00:00", "HHH", "BUY", "normal", "cycle", "saute", {}),
    ("2026-10-08T09:00:00+00:00", "III", "BUY", "normal", "cycle", "execute", {"suite": {"resultat": "sans_donnees"}}),
    ("2026-10-05T09:00:00+00:00", "JJJ", "BUY", "normal", "cycle", "execute", {}),     # avant R2
]
INTERDITS = re.compile(r"rendement|moyenne|taux|%|verdict|ALERTE|FRAGILE|SOLIDE|facteur|×|pnl|gain|perte|"
                       r"fréquence|win|IC95|bootstrap", re.I)


def registre(chemin: str, lignes=LIGNES) -> None:
    conn = sqlite3.connect(chemin)
    conn.executescript(SCHEMA)
    precedent = GENESE
    for h, ticker, decision, style, origine, statut, autres in lignes:
        contenu = {"origine": origine, "pipeline": {"statut": statut, "verdicts": {"pre_mortem": "ALERTE"}},
                   "suite": {"resultat": "refusee"}, **autres}
        ligne = {"horodatage": h, "type": "decision", "cycle": "tactical", "passage_id": "p", "ticker": ticker,
                 "decision": decision, "style": style, "score": 2.5, "confiance": 7, "prix": 100.0,
                 "position_id": None, "parametres": None, "version_code": "test", "contenu": _canon(contenu),
                 "hash_precedent": precedent}
        precedent = empreinte_ligne(ligne)
        conn.execute(f"INSERT INTO registre ({', '.join(COLONNES)}, hash) VALUES ({', '.join('?' * (len(COLONNES) + 1))})",
                     [ligne[c] for c in COLONNES] + [precedent])
    conn.commit()
    conn.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.chemin = os.path.join(self.dossier.name, "registre.db")
        registre(self.chemin)

    def tearDown(self):
        self.dossier.cleanup()

    def lancer(self, argv=()) -> tuple[int, str]:
        sortie = io.StringIO()
        with mock.patch.object(q, "CHEMIN", self.chemin), redirect_stdout(sortie):
            code = q.main(list(argv))
        return code, sortie.getvalue()


class TestDefinition(Base):
    def test_couples_examines_et_replis_a_part(self):
        conn = sqlite3.connect(f"file:{self.chemin}?mode=ro", uri=True)
        decisions = q.decisions_du_registre(conn)
        conn.close()
        self.assertTrue(all(set(d) == {"ticker", "jour", "action", "statut"} for d in decisions))  # ni verdict ni prix
        examines, prudents = q.couples(decisions)
        self.assertEqual(examines, {("AAA", date(2026, 10, 7), "BUY"), ("AAA", date(2026, 10, 7), "SELL"),
                                    ("BBB", date(2026, 10, 12), "BUY"), ("DDD", date(2026, 10, 8), "SELL")})
        self.assertEqual(prudents, {("CCC", date(2026, 10, 8), "BUY")})
        self.assertEqual(q.par_semaine(examines, prudents), {"2026-S41": (3, 1), "2026-S42": (1, 0)})

    def test_jour_de_lisbonne(self):
        self.assertEqual(q.jour_lisbonne("2026-10-11T23:30:00+00:00"), date(2026, 10, 12))  # UTC+1 en octobre
        self.assertEqual(q.jour_lisbonne("2026-12-01T23:30:00+00:00"), date(2026, 12, 1))   # UTC+0 en hiver
        self.assertEqual(q.jour_lisbonne("2026-10-11T23:30:00"), date(2026, 10, 12))        # sans fuseau : UTC

    def test_constat_des_logs(self):
        ligne = "{} | INFO     | agents.decision_engine | Taille {} ajustée par pipeline : 1.00 → {} ({})"
        logs = [ligne.format("2026-10-01 10:00:00", "AAA", "0.17", "Pré-mortem ALERTE (-50%)"),
                ligne.format("2026-10-01 18:00:00", "AAA", "0.17", "Pré-mortem ALERTE (-50%)"),
                ligne.format("2026-10-02 10:00:00", "AAA", "0.35", "Métacognition FRAGILE (-50%)"),
                ligne.format("2026-10-06 14:01:11", "BBB", "0.50", "Pipeline indisponible (LLM KO)"),
                ligne.format("2026-10-06 19:00:00", "CCC", "0.17", "Pré-mortem ALERTE (-50%)"),  # après c4908bb
                "2026-10-01 10:00:00 | INFO     | cycle_tactical | 📋 ÉTAPE 4 — Analyse watchlist"]
        examines, prudents = q.couples(q.decisions_du_constat(logs))
        self.assertEqual(examines, {("AAA", date(2026, 10, 1), None), ("AAA", date(2026, 10, 2), None)})
        self.assertEqual(prudents, {("BBB", date(2026, 10, 6), None)})


class TestSortie(Base):
    def test_compteurs_seulement(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("2026-S41          3                  1", texte)
        self.assertIn("4 couple(s) examiné(s), 1 couple(s) en repli Prudent seul (hors minimum)", texte)
        self.assertIn("Minimum requis : 40 couples examinés", texte)
        self.assertIn("Lecture prévue : 03/11/2026 ; échéance : 01/12/2026", texte)
        self.assertIsNone(INTERDITS.search(texte), INTERDITS.search(texte))

    def test_aucun_champ_de_rendement_meme_avec_des_lignes_qui_en_portent(self):
        lignes = [l[:6] + ({"rendement": 0.031, "moyenne": 1.2, "verdict": "ALERTE"},) for l in LIGNES]
        registre(self.chemin + "2", lignes)
        self.chemin += "2"
        _, texte = self.lancer()
        self.assertIsNone(INTERDITS.search(texte), INTERDITS.search(texte))

    def test_lecture_seule(self):
        with open(self.chemin, "rb") as f:
            avant = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(self.lancer()[0], 0)
        with open(self.chemin, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), avant)
        conn = sqlite3.connect(f"file:{self.chemin}?mode=ro", uri=True)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE t (x)")
        conn.close()

    def test_registre_absent(self):
        self.chemin = os.path.join(self.dossier.name, "absent.db")
        code, texte = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("Registre inaccessible", texte)
        self.assertFalse(os.path.exists(self.chemin))  # mode=ro : jamais créé


if __name__ == "__main__":
    unittest.main()
