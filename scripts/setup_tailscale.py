"""
scripts/setup_tailscale.py — Expose le dashboard AlphaSignal sur le tailnet
via Tailscale Serve (accès distant privé en HTTPS, jamais public).

Usage : .venv\\Scripts\\python.exe scripts\\setup_tailscale.py

Important :
- Ne touche jamais à Tailscale Funnel (exposition publique Internet) :
  ce script n'appelle que `tailscale serve`.
- Le dashboard Flask continue d'écouter sur 0.0.0.0 (accès Wi-Fi local
  existant, voir CLAUDE.md) : on ne le fait PAS basculer sur 127.0.0.1.
  Tailscale Serve proxifie en interne via l'interface Tailscale, donc
  aucune règle de pare-feu Windows supplémentaire n'est nécessaire — ce
  n'est pas une exposition sur le réseau physique.
- Idempotent : si le port est déjà proxifié, ne relance pas `serve`.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # charge .env (load_dotenv) — nécessaire pour lire DASHBOARD_PORT
from utils.tailscale import etat_connexion, localiser_tailscale, serve_deja_configure

PORT_HTTPS = 443


def main() -> int:
    try:
        tailscale_exe = localiser_tailscale()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    try:
        etat = etat_connexion(tailscale_exe)
    except Exception as e:
        print(f"❌ Impossible de vérifier l'état Tailscale : {e}")
        return 1

    if not etat["connecte"]:
        print(f"❌ Node Tailscale non connecté (BackendState={etat['backend_state']}).")
        print("   → lance : tailscale up")
        return 1

    # Même lecture que dashboard/app.py : aucun port en dur ici.
    port = int(os.getenv("DASHBOARD_PORT", "8080"))

    if serve_deja_configure(tailscale_exe, port):
        print(f"✅ Tailscale Serve proxifie déjà le port {port} — rien à faire.")
    else:
        print(f"→ Configuration de Tailscale Serve (HTTPS {PORT_HTTPS} → 127.0.0.1:{port})...")
        result = subprocess.run(
            [tailscale_exe, "serve", "--bg", f"--https={PORT_HTTPS}", str(port)],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            print(f"❌ Échec `tailscale serve` : {(result.stderr or result.stdout).strip()}")
            return 1
        print(f"✅ Tailscale Serve configuré (port {port} → HTTPS {PORT_HTTPS}).")

    if etat["dns_name"]:
        print(f"\n🌐 Accès distant : https://{etat['dns_name']}/")
    else:
        print("\n⚠️  DNSName introuvable — vérifie MagicDNS (`tailscale status`).")

    print("\nRappel : Funnel (exposition publique) n'est jamais activé par ce script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
