#!/bin/bash
# scripts/install_v4.sh — Installation/désinstallation des 6 plists launchd v4
#
# Usage :
#   ./scripts/install_v4.sh install    → installe les 6 cycles
#   ./scripts/install_v4.sh uninstall  → décharge tout

set -eu

LAUNCH_DIR="$HOME/Library/LaunchAgents"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
CYCLES=(critical tactical strategic daily weekly cleanup dashboard)

CMD="${1:-install}"

case "$CMD" in
install)
    echo "🚀 Installation des 6 cycles launchd v4..."
    mkdir -p "$LAUNCH_DIR"
    chmod +x "${PROJECT_DIR}/scripts/run_mac.sh"

    for cycle in "${CYCLES[@]}"; do
        plist_src="${PROJECT_DIR}/scripts/com.alphasignal.${cycle}.plist"
        plist_dst="${LAUNCH_DIR}/com.alphasignal.${cycle}.plist"

        if [ ! -f "$plist_src" ]; then
            echo "  ⚠️  Plist source manquant : $plist_src"
            continue
        fi

        # Décharger si déjà chargé
        launchctl unload "$plist_dst" 2>/dev/null || true

        cp "$plist_src" "$plist_dst"
        launchctl load "$plist_dst"
        echo "  ✓ ${cycle} installé"
    done

    echo ""
    echo "📋 Vérification :"
    launchctl list | grep alphasignal || echo "  (aucun job actif)"
    echo ""
    echo "✅ Installation terminée. Les cycles tourneront automatiquement."
    ;;

uninstall)
    echo "🛑 Désinstallation des 6 cycles launchd v4..."
    for cycle in "${CYCLES[@]}"; do
        plist_dst="${LAUNCH_DIR}/com.alphasignal.${cycle}.plist"
        if [ -f "$plist_dst" ]; then
            launchctl unload "$plist_dst" 2>/dev/null || true
            rm "$plist_dst"
            echo "  ✓ ${cycle} retiré"
        fi
    done
    echo "✅ Désinstallation terminée."
    ;;

*)
    echo "Usage : $0 {install|uninstall}"
    exit 1
    ;;
esac
