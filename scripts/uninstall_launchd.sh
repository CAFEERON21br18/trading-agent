#!/bin/bash
# ============================================================
# AlphaSignal — Désinstallation du scheduler launchd
# ============================================================

PLIST_NAME="com.alphasignal.daily"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "AlphaSignal — Désinstallation launchd"

if [ -f "$PLIST_DEST" ]; then
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    rm "$PLIST_DEST"
    echo "✓ Scheduler désinstallé"
else
    echo "→ Aucune installation trouvée"
fi
