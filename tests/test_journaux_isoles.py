"""
tests/test_journaux_isoles.py — TODO §28 : aucun test n'écrit dans logs/ (production).

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_journaux_isoles -v
1. chaque module tests/test_*.py qui importe du code du dépôt appelle isoler_journaux() avant
   (lecture du source, sans l'exécuter) ;
2. pendant les tests, aucun handler de fichier ne pointe vers logs/ du dépôt, et utils.logger
   écrit ailleurs (en suite complète : vérifié après l'import de tous les modules) ;
3. l'appel est idempotent : un second appel garde le même dossier.
"""

import ast
import glob
import logging
import os
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from utils import logger as journal

PAQUETS = {"agents", "alerts", "config", "dashboard", "main", "scripts", "tests", "utils"}
LOGS = os.path.normcase(os.path.join(RACINE, "logs")) + os.sep


def _imports_du_depot(noeud: ast.AST) -> list[tuple[int, str]]:
    """Imports du dépôt exécutés par une instruction de premier niveau (hors corps de def et class)."""
    out, pile = [], [noeud]
    while pile:
        n = pile.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        noms = ([a.name for a in n.names] if isinstance(n, ast.Import)
                else [n.module or ""] if isinstance(n, ast.ImportFrom) and not n.level else [])
        out += [(n.lineno, nom) for nom in noms
                if nom.split(".")[0] in PAQUETS and nom != "tests.journaux_isoles"]
        pile.extend(ast.iter_child_nodes(n))
    return out


def _est_l_appel(instr: ast.stmt) -> bool:
    return (isinstance(instr, ast.Expr) and isinstance(instr.value, ast.Call)
            and getattr(instr.value.func, "id", None) == "isoler_journaux")


def imports_avant_l_appel(source: str) -> tuple[bool, list[tuple[int, str]]]:
    """(appel présent, imports du dépôt exécutés avant lui ou sans lui)."""
    avant = []
    for instr in ast.parse(source).body:
        if _est_l_appel(instr):
            return True, avant
        avant += _imports_du_depot(instr)
    return False, avant


class TestChaqueModuleAppelleIsolerJournaux(unittest.TestCase):
    def test_appel_avant_tout_import_du_depot(self):
        modules = sorted(glob.glob(os.path.join(RACINE, "tests", "test_*.py")))
        self.assertGreater(len(modules), 20)
        for chemin in modules:
            with self.subTest(module=os.path.basename(chemin)):
                # sans appel, « avant » liste tous les imports : permis seulement s'il n'y en a aucun
                with open(chemin, encoding="utf-8") as f:
                    appel, avant = imports_avant_l_appel(f.read())
                self.assertEqual(avant, [], "import du dépôt avant isoler_journaux()" if appel
                                 else "import du dépôt sans isoler_journaux()")

    def test_detecte_un_import_trop_tot(self):
        appel = "from tests.journaux_isoles import isoler_journaux\nisoler_journaux()\n"
        self.assertEqual(imports_avant_l_appel("import os\nfrom utils import database\n" + appel),
                         (True, [(2, "utils")]))
        self.assertEqual(imports_avant_l_appel("try:\n    import config\nexcept Exception:\n    pass\n"),
                         (False, [(2, "config")]))
        self.assertEqual(imports_avant_l_appel(appel + "def f():\n    import config\n"), (True, []))


class TestAucunHandlerVersLogs(unittest.TestCase):
    def test_fichiers_de_utils_logger_hors_de_logs(self):
        for chemin in (journal.LOG_FILE_MAIN, journal.LOG_FILE_ERROR):
            self.assertFalse(os.path.normcase(os.path.abspath(chemin)).startswith(LOGS), chemin)

    def test_aucun_handler_de_fichier_vers_logs(self):
        loggers = [logging.getLogger()] + [l for l in logging.Logger.manager.loggerDict.values()
                                           if isinstance(l, logging.Logger)]
        vers_logs = [(lg.name, h.baseFilename) for lg in loggers for h in lg.handlers
                     if isinstance(h, logging.FileHandler)
                     and os.path.normcase(h.baseFilename).startswith(LOGS)]
        self.assertEqual(vers_logs, [])

    def test_nouveau_logger_hors_de_logs(self):
        lg = journal.get_logger("tests.journaux_isoles.temoin")
        fichiers = [h.baseFilename for h in lg.handlers if isinstance(h, logging.FileHandler)]
        self.assertTrue(fichiers)
        self.assertFalse(any(os.path.normcase(f).startswith(LOGS) for f in fichiers), fichiers)

    def test_idempotent(self):
        self.assertEqual(isoler_journaux(), isoler_journaux())


if __name__ == "__main__":
    unittest.main()
