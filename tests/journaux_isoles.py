"""
tests/journaux_isoles.py — Logs des tests hors de logs/ (production), pour toute la suite (TODO §28).

Chaque module de test l'appelle avant d'importer le code du dépôt :
    from tests.journaux_isoles import isoler_journaux
    isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)
Le premier appel du processus envoie les fichiers de utils.logger (LOG_FILE_MAIN, LOG_FILE_ERROR)
vers un dossier temporaire, y compris les handlers des loggers déjà créés ; les appels suivants ne
font rien. La redirection n'est jamais défaite pendant les tests : ni l'ordre d'import des modules
(discover, ordre inverse, module seul) ni un tearDownModule ne la changent. Le dossier est fermé
et supprimé à la sortie du processus. Vérifié par tests/test_journaux_isoles.py.
"""

import atexit
import shutil
import tempfile

_DOSSIER = None


def isoler_journaux() -> str:
    """Dossier des logs des tests, créé au premier appel du processus."""
    global _DOSSIER
    if _DOSSIER is None:
        from scripts._banc_fichiers import journaux_detaches
        dossier = tempfile.mkdtemp(prefix="alphasignal_tests_logs_")
        bloc = journaux_detaches(dossier)
        bloc.__enter__()
        atexit.register(_fermer, bloc, dossier)
        _DOSSIER = dossier
    return _DOSSIER


def _fermer(bloc, dossier: str) -> None:
    bloc.__exit__(None, None, None)
    shutil.rmtree(dossier, ignore_errors=True)
