"""
utils/tailscale.py — Aide commune pour l'accès distant AlphaSignal via
Tailscale Serve : scripts/setup_tailscale.py et scripts/teardown_tailscale.py.

Important : ceci couvre uniquement Tailscale SERVE (partage privé, interne
au tailnet). Tailscale FUNNEL (exposition publique sur Internet) n'est
jamais utilisé ici et ne doit pas l'être.
"""

import json
import os
import subprocess

# Chemin de la CLI Tailscale sous Windows. Configurable via la variable
# d'environnement TAILSCALE_EXE_PATH si l'installation n'est pas standard.
CHEMIN_TAILSCALE_DEFAUT = r"C:\Program Files\Tailscale\tailscale.exe"


def localiser_tailscale() -> str:
    """Retourne le chemin de tailscale.exe. Échec explicite s'il est introuvable."""
    chemin = os.getenv("TAILSCALE_EXE_PATH", CHEMIN_TAILSCALE_DEFAUT)
    if not os.path.isfile(chemin):
        raise FileNotFoundError(
            f"tailscale.exe introuvable à '{chemin}'. "
            f"Vérifie l'installation ou définis TAILSCALE_EXE_PATH dans l'environnement."
        )
    return chemin


def etat_connexion(tailscale_exe: str) -> dict:
    """
    Interroge `tailscale status --json`.
    Retourne {connecte: bool, backend_state: str, dns_name: str|None}.
    """
    result = subprocess.run([tailscale_exe, "status", "--json"],
                             capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"tailscale status a échoué : {result.stderr.strip()}")
    data = json.loads(result.stdout)
    backend_state = data.get("BackendState", "?")
    self_node = data.get("Self", {})
    dns_name = (self_node.get("DNSName") or "").rstrip(".") or None
    connecte = backend_state == "Running" and bool(self_node.get("Online"))
    return {"connecte": connecte, "backend_state": backend_state, "dns_name": dns_name}


def serve_deja_configure(tailscale_exe: str, port: int) -> bool:
    """
    True si `tailscale serve` proxifie déjà ce port (idempotence) : évite
    de relancer `tailscale serve` à chaque exécution du script.
    """
    result = subprocess.run([tailscale_exe, "serve", "status", "--json"],
                             capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return False
    sortie = result.stdout
    return f"127.0.0.1:{port}" in sortie or f"localhost:{port}" in sortie
