"""
tests/test_vault_trading.py — Phase 2, partie A : mémoire de trading dans le vault Obsidian
(scripts/sync_vault_trading.py, agents/vault/).

Bases synthétiques (registre, positions, instantanés, et des tables real_* piégées) : premier passage,
idempotence (rien n'est réécrit), pas de doublon (une note par actif, jour et action), note manuelle
préservée, écriture atomique, aucune valeur réelle dans le vault ni aucune requête sur real_*, bases
intactes, intuitions modifiées seulement, passage du matin seulement.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_vault_trading -v
Toutes les données sont inventées ; dossiers temporaires.
"""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from agents.vault import ecriture
from scripts import sync_vault_trading as svt

REEL = ("ZZREEL-TEST", "Actif réel inventé", "4321.987")  # valeurs piégées des tables real_*
CLES = ["date", "type", "actif", "cycle", "decision", "tags", "genere_par"]
INTUITIONS = ("### 2026-10-12 08:15 UTC — AAA-USD — BUY (intuition)\n- **Score indicateurs** : +1.10\n"
              "- **Override** : décision modifiée vers BUY\n- **Résultat** : ⏳ à remplir après clôture\n"
              "\n### 2026-10-12 09:15 UTC — BBB — SELL (intuition)\n- **Score indicateurs** : -1.40\n"
              "- **Résultat** : ⏳ à remplir après clôture\n")


def decision(h, cycle, ticker, action, resultat="refusee", origine="cycle", source="watchlist", pid=None):
    contenu = {"origine": origine, "source": source, "suite": {"resultat": resultat, "raisons": ["Confiance 6/10 < seuil"],
                                                                **({"position_id": pid} if pid else {})},
               "pipeline": {"statut": "cache"}}
    return (h, "decision", cycle, "p1", ticker, action, "normal", 2.4, 6, 101.5, pid, json.dumps(contenu))


def bases(dossier):
    reg, db = os.path.join(dossier, "registre.db"), os.path.join(dossier, "database.db")
    c = sqlite3.connect(reg)
    c.execute("CREATE TABLE registre (id INTEGER PRIMARY KEY, horodatage TEXT, type TEXT, cycle TEXT, passage_id TEXT, "
              "ticker TEXT, decision TEXT, style TEXT, score REAL, confiance INTEGER, prix REAL, position_id INTEGER, "
              "contenu TEXT)")
    wl = {"WATCHLIST": [["crypto", ["AAA-USD"]], ["cfd", ["CC=F"]], ["stocks", ["BBB"]]]}
    c.executemany("INSERT INTO registre (horodatage, type, cycle, passage_id, ticker, decision, style, score, confiance, "
                  "prix, position_id, contenu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        ("2026-10-06T18:00:00+00:00", "parametres", None, None, None, None, None, None, None, None, None, json.dumps(wl)),
        decision("2026-10-12T06:31:00+00:00", "quotidien", "AAA-USD", "BUY", "ouverte", pid=7),
        decision("2026-10-12T06:45:00+00:00", "tactical", "AAA-USD", "BUY"),
        decision("2026-10-12T07:00:00+00:00", "tactical", "BBB", "SELL"),
        decision("2026-10-12T07:00:00+00:00", "strategique", REEL[0], "SELL", "conseils", "conseiller", "position_reelle"),
        ("2026-10-12T07:00:00+00:00", "decision", "tactical", "p2", "CC=F", "HOLD", "normal", 0.1, 3, 9.0, None, "{}"),
        ("2026-10-12T06:32:00+00:00", "passage", "quotidien", "p1", None, None, None, None, None, None, None,
         json.dumps({"duree_s": 40.0, "ecrites": 3, "erreurs": 0})),
        ("2026-10-13T06:31:00+00:00", "ancre", "quotidien", None, None, None, None, None, None, None, None,
         json.dumps({"jour": "2026-10-12", "derniere_empreinte": "ab" * 32, "lignes": 9, "verification": {"erreurs": 0}}))])
    c.commit(); c.close()
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, ticker TEXT, asset_type TEXT, direction TEXT, status TEXT, "
              "entry_price REAL, entry_date TEXT, quantity REAL, invested_amount REAL, stop_loss REAL, target_1 REAL, "
              "exit_price REAL, exit_date TEXT, pnl_euros REAL, pnl_percent REAL, confidence INTEGER, entry_reason TEXT, "
              "exit_reason TEXT)")
    c.executemany("INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (7, "AAA-USD", "crypto", "LONG", "CLOSED_TP", 100.0, "2026-10-12T06:31:30+00:00", 0.5, 50.0, 95.0, 110.0,
         110.0, "2026-10-13T10:00:00+00:00", 5.0, 10.0, 8, "Score +2.4", "Target 1 atteint"),
        (8, "BBB", "action", "SHORT", "OPEN", 20.0, "2026-10-13T08:00:00+00:00", 1.0, 20.0, 21.0, 18.0,
         None, None, None, None, 8, "Score -2.4", None)])
    c.execute("CREATE TABLE portfolio_snapshots (date TEXT, cash REAL, invested REAL, total_value REAL, "
              "daily_return_percent REAL, cumulative_return_percent REAL, open_positions_count INTEGER)")
    c.execute("INSERT INTO portfolio_snapshots VALUES ('2026-10-12', 950, 50, 1000, 0.1, 0.0, 1)")
    c.execute("CREATE TABLE real_investments (asset TEXT, asset_name TEXT, quantity REAL)")
    c.execute("INSERT INTO real_investments VALUES (?, ?, ?)", (REEL[0], REEL[1], float(REEL[2])))
    c.execute("CREATE TABLE real_advice_log (recommendation TEXT)")
    c.execute("INSERT INTO real_advice_log VALUES (?)", (REEL[1],))
    c.commit(); c.close()
    intu = os.path.join(dossier, "intuition_log.md")
    with open(intu, "w", encoding="utf-8") as f:
        f.write("# Journal\n\n## Entrées\n" + INTUITIONS)
    return reg, db, intu


class TestVault(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.d.cleanup)
        self.reg, self.db, self.intu = bases(self.d.name)
        self.vault = os.path.join(self.d.name, "vault")

    def sync(self):
        return svt.synchroniser(self.vault, self.reg, self.db, self.intu)

    def fichiers(self):
        out = {}
        for racine, _, noms in os.walk(self.vault):
            for n in noms:
                with open(os.path.join(racine, n), encoding="utf-8") as f:
                    out[os.path.relpath(os.path.join(racine, n), self.vault).replace("\\", "/")] = f.read()
        return out

    def test_premier_passage_et_frontmatter(self):
        self.sync()
        f = self.fichiers()
        self.assertEqual(sorted(f), sorted([
            "00-Index.md", "10-Decisions/2026-10-12 AAA-USD BUY.md", "10-Decisions/2026-10-12 BBB SELL.md",
            "20-Actifs/AAA-USD.md", "20-Actifs/BBB.md", "20-Actifs/CC=F.md",
            "30-Intuitions/Intuition 2026-10-12 0815 AAA-USD.md", "40-Cycles/Cycle 2026-10-12.md",
            "50-Positions/Position 7 AAA-USD.md"]))
        for nom, texte in f.items():
            cles = [l.split(":")[0] for l in texte.split("---\n")[1].splitlines()]
            self.assertEqual(cles, CLES, nom)
        note = f["10-Decisions/2026-10-12 AAA-USD BUY.md"]
        self.assertIn("[[AAA-USD]] · [[Cycle 2026-10-12]]", note)
        self.assertIn("Passages : 2 (quotidien ×1, tactical ×1)", note)
        self.assertIn("[[Position 7 AAA-USD]]", note)
        self.assertIn("Paper trading uniquement", note)

    def test_idempotence_sans_doublon(self):
        premier = self.sync()
        avant = {n: os.path.getmtime(os.path.join(self.vault, n)) for n in self.fichiers()}
        second = self.sync()
        self.assertEqual((second["ecrites"], second["inchangees"]), (0, premier["notes"]))
        self.assertEqual(avant, {n: os.path.getmtime(os.path.join(self.vault, n)) for n in self.fichiers()})
        self.assertEqual(len(self.fichiers()), premier["notes"])

    def test_note_manuelle_preservee(self):
        self.sync()
        manuelle = os.path.join(self.vault, "10-Decisions", "2026-10-12 BBB SELL.md")
        gardee = os.path.join(self.vault, "20-Actifs", "AAA-USD.md")
        with open(manuelle, "w", encoding="utf-8") as f:
            f.write("# Mes notes sur BBB\n")
        with open(gardee, encoding="utf-8") as f:
            sans_marqueur = f.read().replace(ecriture.MARQUEUR + "\n", "") + "\nMa remarque.\n"
        with open(gardee, "w", encoding="utf-8") as f:
            f.write(sans_marqueur)
        bilan = self.sync()
        self.assertEqual(sorted(bilan["manuelles"]), ["10-Decisions/2026-10-12 BBB SELL.md", "20-Actifs/AAA-USD.md"])
        self.assertEqual(self.fichiers()["10-Decisions/2026-10-12 BBB SELL.md"], "# Mes notes sur BBB\n")
        self.assertEqual(self.fichiers()["20-Actifs/AAA-USD.md"], sans_marqueur)

    def test_ecriture_atomique(self):
        self.sync()
        chemin = os.path.join(self.vault, "00-Index.md")
        with open(chemin, encoding="utf-8") as f:
            avant = f.read()
        with mock.patch.object(ecriture.os, "replace", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                ecriture.ecrire_notes(self.vault, {"00-Index.md": avant + "changement\n"})
        with open(chemin, encoding="utf-8") as f:
            self.assertEqual(f.read(), avant)
        self.assertFalse([n for n in os.listdir(self.vault) if n.endswith(".tmp")])

    def test_aucune_valeur_reelle_ni_requete_real(self):
        requetes, connecter = [], sqlite3.connect

        def espion(*a, **k):
            conn = connecter(*a, **k)
            conn.set_trace_callback(requetes.append)
            return conn
        def empreintes():
            sortie = {}
            for p in (self.reg, self.db):
                with open(p, "rb") as f:
                    sortie[p] = hashlib.sha256(f.read()).hexdigest()
            return sortie
        avant = empreintes()
        with mock.patch.object(sqlite3, "connect", side_effect=espion):
            self.sync()
        self.assertTrue(requetes)
        self.assertFalse([r for r in requetes if "real_" in r.lower()])
        tout = "\n".join(self.fichiers().values())
        for valeur in REEL + (REEL[2].replace(".", ","),):
            self.assertNotIn(valeur, tout)
        self.assertEqual(avant, empreintes())  # bases intactes (mode=ro)

    def test_matin_seulement(self):
        lisbonne = ZoneInfo("Europe/Lisbon")
        with mock.patch.object(svt, "synchroniser", return_value={"notes": 1}) as s:
            self.assertEqual(svt.synchroniser_du_matin(datetime(2026, 10, 19, 7, 31, tzinfo=lisbonne)), {"notes": 1})
            self.assertIsNone(svt.synchroniser_du_matin(datetime(2026, 10, 19, 12, 0, tzinfo=lisbonne)))
        self.assertEqual(s.call_count, 1)


if __name__ == "__main__":
    unittest.main()
