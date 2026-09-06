#!/usr/bin/env python3
"""
scripts/show_access_urls.py — Affiche toutes les URLs d'accès au dashboard.
Local, WiFi maison, Tailscale (partout). v5.6.0.

Usage : python3 scripts/show_access_urls.py
"""

import subprocess
import socket
import os
import shutil

PORT = int(os.getenv("DASHBOARD_PORT", "8080"))


def get_local_ip() -> str | None:
    """IP LAN du Mac (celle affichée dans Réglages > WiFi)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_tailscale_ip() -> str | None:
    """IP Tailscale 100.x.x.x du Mac, si Tailscale installé et connecté."""
    if shutil.which("tailscale") is None:
        return None
    try:
        r = subprocess.run(["tailscale", "ip", "-4"],
                            capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        out = (r.stdout or "").strip()
        return out.split("\n")[0] if out else None
    except Exception:
        return None


def get_tailscale_hostname() -> str | None:
    """Nom MagicDNS du Mac (ex: alphasignal-mac.tailXXXX.ts.net) si activé."""
    if shutil.which("tailscale") is None:
        return None
    try:
        r = subprocess.run(["tailscale", "status", "--json"],
                            capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        import json
        data = json.loads(r.stdout)
        self_ = data.get("Self", {})
        dns_name = self_.get("DNSName", "").rstrip(".")
        return dns_name if dns_name else None
    except Exception:
        return None


def dashboard_repond(url: str) -> bool:
    """Ping HTTP rapide (2s) pour vérifier que l'URL répond."""
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=2) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def _url_line(label: str, url: str, note: str = "") -> str:
    ok = dashboard_repond(url)
    marker = "✅" if ok else "❌"
    return f"  {marker} {label:20s} : {url}   {note}"


def main() -> int:
    print("═══════════════════════════════════════════════════════════")
    print("  📊 ALPHASIGNAL — URLs d'accès au dashboard")
    print("═══════════════════════════════════════════════════════════")
    print()

    # 1. Localhost (sur le Mac)
    print(_url_line("Local (ce Mac)", f"http://localhost:{PORT}"))
    print(_url_line("Local IP",       f"http://127.0.0.1:{PORT}"))
    print()

    # 2. WiFi maison
    lan = get_local_ip()
    if lan:
        print("  Sur le même WiFi (téléphone à la maison) :")
        print(_url_line("WiFi maison", f"http://{lan}:{PORT}"))
    else:
        print("  ⚠️  IP LAN non détectée (pas connecté au WiFi ?)")
    print()

    # 3. Tailscale (partout : 4G, autre WiFi, etc.)
    ts_ip   = get_tailscale_ip()
    ts_host = get_tailscale_hostname()
    if ts_ip or ts_host:
        print("  Partout (avec Tailscale actif sur les 2 appareils) :")
        if ts_ip:
            print(_url_line("Tailscale IP", f"http://{ts_ip}:{PORT}"))
        if ts_host:
            print(_url_line("Tailscale DNS", f"http://{ts_host}:{PORT}",
                             note="(MagicDNS)"))
    else:
        print("  🔒 Tailscale non installé ou non connecté")
        print("     → https://tailscale.com/download/mac (gratuit, perso)")
        print("     → Puis relancer ce script pour voir l'URL")
    print()
    print("═══════════════════════════════════════════════════════════")
    print("  💡 iPhone : ouvrir l'URL dans Safari → Partager → 'Sur l'écran d'accueil'")
    print("     Chrome Android : menu ⋮ → 'Installer l'application'")
    print("═══════════════════════════════════════════════════════════")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
