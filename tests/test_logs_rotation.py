"""
tests/test_logs_rotation.py — TODO §1 : un fichier de logs par tâche, rotation sans « Logging error ».

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_logs_rotation -v
Fichiers dans des dossiers temporaires (jamais logs/) ; le verrou réel de Windows (fichier ouvert
par un autre handle) n'est testé que sous Windows.
"""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import journal_rotation as jr
from utils import logger as journal


class TestNomTache(unittest.TestCase):
    def test_un_nom_par_tache_planifiee(self):
        for script, tache in ((r"scripts\cycle_critical.py", "critical"), ("scripts/cycle_tactical.py", "tactical"),
                              (r"scripts\cycle_strategic.py", "strategic"), (r"scripts\cycle_daily.py", "daily"),
                              (r"scripts\cycle_weekly.py", "weekly"), (r"scripts\cleanup.py", "cleanup"),
                              (r"dashboard\app.py", "dashboard"), (os.path.join(RACINE, "dashboard", "app.py"), "dashboard")):
            self.assertEqual(journal.nom_tache(script), tache, script)

    def test_autres_lancements(self):
        for script, tache in (("scripts/jev_bilan.py", "jev_bilan"), ("-c", "python"), ("", "python"),
                              (os.path.join("lib", "unittest", "__main__.py"), "unittest"),
                              ("app.py", "app"), ("mon script!.py", "mon_script")):
            self.assertEqual(journal.nom_tache(script), tache, script)

    def test_fichiers_de_la_tache(self):
        principal, erreurs = journal.fichiers_de("tactical")
        self.assertEqual((os.path.basename(principal), os.path.basename(erreurs)), ("tactical.log", "tactical_errors.log"))
        self.assertEqual(os.path.dirname(principal), journal.LOGS_DIR)

    def test_alerte_de_daily_routine_cite_son_fichier(self):
        _, erreurs = journal.fichiers_de(journal.nom_tache(r"scripts\daily_routine.py"))
        with open(os.path.join(RACINE, "scripts", "daily_routine.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertIn("logs\\\\" + os.path.basename(erreurs), source)  # chemin Windows relatif au dépôt
        self.assertNotIn("~/trading-agent", source)

    def test_handlers_de_rotation_tolerante(self):
        lg = journal.get_logger("tests.logs_rotation.temoin")
        fichiers = [h for h in lg.handlers if isinstance(h, logging.FileHandler)]
        self.assertEqual(len(fichiers), 2)
        self.assertTrue(all(isinstance(h, jr.RotationTolerante) for h in fichiers))


class BaseRotation(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.chemin = os.path.join(self.dossier.name, "tache.log")
        self.h = jr.RotationTolerante(self.chemin, maxBytes=1000, backupCount=3, encoding="utf-8")
        self.h.setFormatter(logging.Formatter("%(message)s"))
        self.erreurs = []
        self.h.handleError = self.erreurs.append  # « --- Logging error --- » sinon

    def tearDown(self):
        self.h.close()
        self.dossier.cleanup()

    def ecrire(self, n: int, prefixe: str = "ligne") -> None:
        for i in range(n):
            self.h.emit(logging.makeLogRecord({"msg": f"{prefixe} {i:04d} " + "x" * 40}))

    def lignes(self) -> list[str]:
        out = []
        for f in sorted(os.listdir(self.dossier.name)):
            with open(os.path.join(self.dossier.name, f), encoding="utf-8") as fh:
                out += fh.read().splitlines()
        return out

    def lire(self, suffixe: str) -> str:
        with open(self.chemin + suffixe, encoding="utf-8") as f:
            return f.read()

    def fichiers(self) -> list[str]:
        return sorted(os.listdir(self.dossier.name))


class TestRotation(BaseRotation):
    def test_rotation_normale_garde_backupcount_sauvegardes(self):
        self.ecrire(200)
        self.assertEqual(self.fichiers(), ["tache.log", "tache.log.1", "tache.log.2", "tache.log.3"])
        self.assertLess(os.path.getsize(self.chemin), 1000)
        self.assertEqual(self.erreurs, [])

    def test_renommage_refuse_rien_deplace_ligne_ecrite_reessai_plus_tard(self):
        self.ecrire(40)  # tache.log.1 existe
        sauvegarde = self.lire(".1")
        vrai = os.replace

        def refus(src, dst):
            if src == self.chemin:
                raise PermissionError(32, "fichier ouvert par un autre processus")
            return vrai(src, dst)
        with mock.patch.object(jr.os, "replace", refus):
            self.ecrire(40, "pendant")
        self.assertEqual(self.erreurs, [])
        self.assertGreater(self.h.echecs, 0)
        self.assertEqual(self.lire(".1"), sauvegarde)  # aucune sauvegarde perdue
        self.assertEqual(sum(l.startswith("pendant") for l in self.lignes()), 40)  # toutes écrites
        self.assertGreater(os.path.getsize(self.chemin), 1000)  # rotation remise à plus tard
        with mock.patch.object(jr.time, "monotonic", return_value=self.h.prochain_essai + 1):
            self.ecrire(1, "apres")
        self.assertLess(os.path.getsize(self.chemin), 1000)
        self.assertEqual(self.erreurs, [])

    def test_rotation_interrompue_terminee_au_prochain_essai(self):
        self.ecrire(40)
        with open(self.h.attente, "w", encoding="utf-8") as f:
            f.write("en attente\n")
        self.h.doRollover()
        self.assertFalse(os.path.exists(self.h.attente))
        self.assertEqual(self.lire(".1"), "en attente\n")
        self.assertEqual(self.erreurs, [])

    @unittest.skipUnless(os.name == "nt", "verrou de renommage propre à Windows")
    def test_fichier_ouvert_ailleurs_sous_windows(self):
        autre = open(self.chemin, "a", encoding="utf-8")  # comme un autre processus ou un lecteur
        try:
            self.ecrire(60, "ouvert")
            self.assertEqual(self.erreurs, [])
            self.assertGreater(self.h.echecs, 0)
            self.assertEqual(sum(l.startswith("ouvert") for l in self.lignes()), 60)
        finally:
            autre.close()
        with mock.patch.object(jr.time, "monotonic", return_value=self.h.prochain_essai + 1):
            self.ecrire(1, "ferme")
        self.assertLess(os.path.getsize(self.chemin), 1000)
        self.assertEqual(self.erreurs, [])


ECRIVAIN = textwrap.dedent("""
    import logging, sys
    sys.path.insert(0, sys.argv[1])
    from utils.journal_rotation import RotationTolerante
    h = RotationTolerante(sys.argv[2], maxBytes=20000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("ecrivain")
    lg.addHandler(h)
    for i in range(1500):
        lg.warning("%s %05d %s", sys.argv[3], i, "y" * 60)
""")


class TestDeuxProcessus(unittest.TestCase):
    def test_deux_taches_en_parallele_rotation_sans_erreur(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            procs = [subprocess.Popen([sys.executable, "-c", ECRIVAIN, RACINE, os.path.join(d, f"{t}.log"), t],
                                      stderr=subprocess.PIPE, text=True) for t in ("tactical", "dashboard")]
            stderr = [p.communicate(timeout=120)[1] for p in procs]
            self.assertEqual([p.returncode for p in procs], [0, 0], stderr)
            self.assertFalse(any("Logging error" in e for e in stderr), stderr)
            for t in ("tactical", "dashboard"):
                self.assertTrue(os.path.exists(os.path.join(d, f"{t}.log.3")), sorted(os.listdir(d)))
                self.assertLess(os.path.getsize(os.path.join(d, f"{t}.log")), 20000)


if __name__ == "__main__":
    unittest.main()
