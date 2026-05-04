#!/bin/bash
# scripts/run_mac.sh — Wrapper macOS pour les cycles AlphaSignal
# Usage : ./scripts/run_mac.sh <cycle>
#   où <cycle> = critical | tactical | strategic | daily | weekly | cleanup | check_status
#
# Configure le PATH, charge le venv (miniconda3) et lance le script Python.
# Utilisé par launchd pour démarrer chaque cycle au bon moment.

set -e
set -u

# ── Chemins ─────────────────────────────────────────────────────────────
PROJECT_DIR="/Users/ruby-rosa/trading-agent"
PYTHON_BIN="/Users/ruby-rosa/miniconda3/bin/python3"
SCRIPTS_DIR="${PROJECT_DIR}/scripts"
LOG_DIR="${PROJECT_DIR}/logs"

# ── Validation arguments ────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage : $0 <cycle>"
    echo "Cycles disponibles : critical, tactical, strategic, daily, weekly, cleanup, check_status"
    exit 1
fi

CYCLE="$1"
SCRIPT="${SCRIPTS_DIR}/cycle_${CYCLE}.py"

# Cas spéciaux : cleanup et check_status n'ont pas le préfixe cycle_
case "$CYCLE" in
    cleanup|check_status)
        SCRIPT="${SCRIPTS_DIR}/${CYCLE}.py"
        ;;
esac

if [ ! -f "$SCRIPT" ]; then
    echo "❌ Script introuvable : $SCRIPT"
    exit 1
fi

# ── Environnement ───────────────────────────────────────────────────────
export PATH="/Users/ruby-rosa/miniconda3/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"

# ── Lancement ──────────────────────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lancement cycle ${CYCLE}"
exec "$PYTHON_BIN" "$SCRIPT"
