"""
dashboard/demarrage.py — Un seul dashboard à la fois sur le port.

Werkzeug lie son socket avec SO_REUSEADDR ; sous Windows, ce réglage laisse un second serveur se
lier au MÊME port sans erreur : deux dashboards écoutent alors ensemble et les requêtes vont à l'un
ou à l'autre. Avant app.run, port_occupe() teste donc le port (connexion, puis liaison exclusive
SO_EXCLUSIVEADDRUSE) : s'il est pris, le démarrage s'arrête proprement (code 0, message clair dans
logs/dashboard.log et la sortie de la tâche) au lieu de doubler le serveur.
"""

import socket


def _cible(hote: str) -> str:
    return {"0.0.0.0": "127.0.0.1", "": "127.0.0.1", "::": "::1"}.get(hote, hote)


def port_occupe(hote: str, port: int) -> str | None:
    """Raison pour laquelle le port est pris, ou None s'il est libre."""
    try:
        with socket.create_connection((_cible(hote), port), timeout=1):
            return "un serveur y répond déjà"
    except OSError:
        pass
    famille = socket.AF_INET6 if ":" in hote else socket.AF_INET
    s = socket.socket(famille, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows : refuse de partager le port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((hote, port))
        return None
    except OSError as e:
        return f"liaison impossible ({e})"
    finally:
        s.close()


def port_libre_ou_arret(hote: str, port: int, logger) -> bool:
    """Vrai si le dashboard peut démarrer ; sinon journalise pourquoi (l'appelant sort en code 0)."""
    raison = port_occupe(hote, port)
    if raison is None:
        return True
    logger.warning(f"Port {port} déjà utilisé : {raison}. Un autre dashboard tourne déjà ; ce démarrage "
                   f"s'arrête sans rien lancer (code 0). Pour relancer : arrêter d'abord l'instance en cours.")
    return False
