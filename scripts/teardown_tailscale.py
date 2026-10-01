"""
scripts/teardown_tailscale.py — Désactive l'exposition Tailscale Serve du
dashboard AlphaSignal (reset complet de la config serve).

Usage : .venv\\Scripts\\python.exe scripts\\teardown_tailscale.py
"""

import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tailscale import localiser_tailscale


def main() -> int:
    try:
        tailscale_exe = localiser_tailscale()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    result = subprocess.run([tailscale_exe, "serve", "reset"],
                             capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        print(f"❌ Échec `tailscale serve reset` : {(result.stderr or result.stdout).strip()}")
        return 1

    print("✅ Tailscale Serve réinitialisé — le dashboard n'est plus exposé sur le tailnet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
