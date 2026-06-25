#!/usr/bin/env bash
# scripts/backup_before_update.sh — Sauvegarde complète avant mise à jour macOS.
# Usage : bash scripts/backup_before_update.sh

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATE=$(date +"%Y-%m-%d")
DATETIME=$(date +"%Y-%m-%d_%H%M")
BACKUP_DIR="$HOME/Desktop/alphasignal_backup_${DATETIME}"
mkdir -p "$BACKUP_DIR"

ok()   { printf "✅ %s\n" "$1"; }
warn() { printf "⚠️  %s\n" "$1"; }
info() { printf "ℹ️  %s\n" "$1"; }
hdr()  { printf "\n━━ %s ━━\n" "$1"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AlphaSignal — Sauvegarde avant mise à jour macOS"
echo "  $DATETIME"
echo "  Destination : $BACKUP_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Git commit + push ─────────────────────────────────────────────────
hdr "Git"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    git add . && \
      git commit -m "Sauvegarde avant mise à jour macOS ($DATE)" >/dev/null \
      && ok "Commit créé" \
      || warn "Commit échoué — vérifie l'état git"
else
    info "Working tree propre — aucun commit nécessaire"
fi

if git remote get-url origin >/dev/null 2>&1; then
    REMOTE=$(git remote get-url origin)
    if git push 2>&1 | tail -3; then
        ok "Push réussi vers $REMOTE"
    else
        warn "Push échoué — vérifie credentials. Commits locaux préservés."
    fi
else
    warn "AUCUN REMOTE git configuré."
    warn "→ Pour ajouter un remote GitHub : git remote add origin <URL>"
    warn "→ Tes commits sont LOCAUX seulement (la mise à jour macOS ne devrait pas les toucher)"
fi

# ── 2. Fichiers critiques ───────────────────────────────────────────────
hdr "Fichiers critiques → $BACKUP_DIR"

if [ -f data/database.db ]; then
    cp data/database.db "$BACKUP_DIR/database.db"
    ok "data/database.db ($(du -h "$BACKUP_DIR/database.db" | cut -f1))"
else
    warn "data/database.db introuvable"
fi

if [ -f .env ]; then
    cp .env "$BACKUP_DIR/.env"
    chmod 600 "$BACKUP_DIR/.env"
    ok ".env (clés API, permissions 600 — ne PAS partager)"
else
    warn ".env introuvable"
fi

if [ -d memory ]; then
    cp -R memory "$BACKUP_DIR/memory"
    NB=$(find "$BACKUP_DIR/memory" -type f | wc -l | tr -d ' ')
    ok "memory/ ($NB fichiers)"
else
    warn "memory/ introuvable"
fi

if [ -d data/watchlist.json ] || [ -f data/watchlist.json ]; then
    cp data/watchlist.json "$BACKUP_DIR/watchlist.json"
    ok "data/watchlist.json"
fi

# ── 3. Python version ───────────────────────────────────────────────────
hdr "Python"
PYTHON_BIN="/Users/ruby-rosa/miniconda3/bin/python3"
if [ -x "$PYTHON_BIN" ]; then
    PY_VER=$("$PYTHON_BIN" --version 2>&1)
    PY_WHICH=$(command -v python3 2>&1 || echo "non trouvé")
    {
        echo "── État avant mise à jour macOS ──"
        echo "Date          : $DATETIME"
        echo "Python binary : $PYTHON_BIN"
        echo "Version       : $PY_VER"
        echo "which python3 : $PY_WHICH"
        echo
        echo "── Packages installés (clés) ──"
        "$PYTHON_BIN" -m pip list 2>/dev/null | grep -iE "yfinance|pandas|flask|groq|genai|dotenv|schedule" || true
    } > "$BACKUP_DIR/python_info.txt"
    ok "$PY_VER (info sauvegardée dans python_info.txt)"
else
    warn "Python miniconda3 introuvable à $PYTHON_BIN"
fi

# ── 4. LaunchAgents ─────────────────────────────────────────────────────
hdr "LaunchAgents"
LA_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$BACKUP_DIR/launchagents"
if compgen -G "$LA_DIR/com.alphasignal.*.plist" >/dev/null; then
    cp "$LA_DIR"/com.alphasignal.*.plist "$BACKUP_DIR/launchagents/"
    NB=$(ls "$BACKUP_DIR/launchagents" 2>/dev/null | wc -l | tr -d ' ')
    ok "$NB plist(s) AlphaSignal copiés depuis $LA_DIR"
else
    warn "Aucun plist com.alphasignal.* dans $LA_DIR"
fi

launchctl list 2>/dev/null | awk 'NR==1 || /alphasignal/' > "$BACKUP_DIR/launchctl_list.txt"
ACTIFS=$(grep -c alphasignal "$BACKUP_DIR/launchctl_list.txt" 2>/dev/null || echo 0)
ok "$ACTIFS agent(s) actuellement chargés (liste dans launchctl_list.txt)"

# ── 5. Réglages pmset (énergie) ─────────────────────────────────────────
hdr "Énergie (pmset)"
{
    echo "── Réglages courants ──"; pmset -g 2>/dev/null
    echo
    echo "── Wakes programmés ──"; pmset -g sched 2>/dev/null
} > "$BACKUP_DIR/pmset.txt"
ok "Sauvegardé dans pmset.txt"

# ── 6. Résumé ───────────────────────────────────────────────────────────
hdr "RÉSUMÉ"
ls -lh "$BACKUP_DIR"
echo
TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Taille totale : $TOTAL"
echo
ok "Sauvegarde terminée."
echo
echo "👉 Tu peux maintenant lancer la mise à jour macOS."
echo "👉 Après redémarrage : python3 scripts/check_after_update.py"
