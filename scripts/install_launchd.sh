#!/bin/bash
# ============================================================
# AlphaSignal — Installation du scheduler launchd (macOS)
# Lance l'analyse quotidienne automatiquement à 7h30 locale
# ============================================================

set -e

PLIST_NAME="com.alphasignal.daily"
PLIST_SOURCE="/Users/ruby-rosa/trading-agent/scripts/${PLIST_NAME}.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "AlphaSignal — Installation launchd"
echo ""

# Création du dossier LaunchAgents si besoin
mkdir -p "$HOME/Library/LaunchAgents"

# Déchargement si déjà installé (ignorer erreur si pas chargé)
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Copie du plist
cp "$PLIST_SOURCE" "$PLIST_DEST"
echo "✓ Plist copié : $PLIST_DEST"

# Chargement
launchctl load "$PLIST_DEST"
echo "✓ Scheduler chargé"

# Vérification
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "✓ AlphaSignal est actif — prochaine exécution : 7h30 locale"
    echo ""
    echo "Commandes utiles :"
    echo "  • Déclencher manuellement : launchctl start $PLIST_NAME"
    echo "  • Voir le statut          : launchctl list | grep alphasignal"
    echo "  • Désinstaller            : bash scripts/uninstall_launchd.sh"
    echo "  • Logs                    : tail -f ~/trading-agent/logs/alphasignal.log"
else
    echo "✗ Erreur : le scheduler n'est pas chargé correctement"
    exit 1
fi
