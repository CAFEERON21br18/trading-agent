#!/usr/bin/env python3
"""
scripts/check_after_update.py — Vérifs post-mise-à-jour macOS.
Usage : python3 scripts/check_after_update.py
"""

import os
import sys
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

OK   = "✅"
KO   = "❌"
WARN = "⚠️ "

results: list[tuple[str, str, str, str]] = []  # (label, etat, detail, repair)


def check(label: str, etat: str, detail: str = "", repair: str = "") -> None:
    results.append((label, etat, detail, repair))
    print(f"{etat} {label}" + (f" — {detail}" if detail else ""))


def hdr(t: str) -> None:
    print(f"\n━━ {t} ━━")


# ── 1. Python ───────────────────────────────────────────────────────────
hdr("Python")
py = sys.version_info
v = f"{py.major}.{py.minor}.{py.micro}"
if py.major == 3 and py.minor == 11:
    check("Python 3.11", OK, f"v{v}")
elif py.major == 3 and py.minor >= 11:
    check(f"Python {py.major}.{py.minor}", WARN,
          f"v{v} (attendu 3.11 — version différente OK mais réinstalle les deps si problème)",
          "/Users/ruby-rosa/miniconda3/bin/pip install -r requirements.txt --force-reinstall")
else:
    check("Python", KO, f"v{v} trop ancien (minimum 3.11)",
          "Réinstalle miniconda3 ou : brew install python@3.11")

# ── 2. Environnement (miniconda OU venv) ────────────────────────────────
hdr("Environnement Python")
miniconda = Path("/Users/ruby-rosa/miniconda3/bin/python3")
venv_a = ROOT / "venv" / "bin" / "python3"
venv_b = ROOT / ".venv" / "bin" / "python3"
if miniconda.exists():
    out = subprocess.run([str(miniconda), "--version"], capture_output=True, text=True)
    check("miniconda3", OK, f"{miniconda} ({out.stdout.strip()})")
elif venv_a.exists():
    check("venv", OK, str(venv_a))
elif venv_b.exists():
    check(".venv", OK, str(venv_b))
else:
    check("Environnement Python", KO, "ni miniconda3 ni venv détecté",
          "cd ~/trading-agent && python3 -m venv venv && "
          "source venv/bin/activate && pip install -r requirements.txt")

# ── 3. Dépendances ──────────────────────────────────────────────────────
hdr("Dépendances Python")
deps = [
    ("yfinance",        "yfinance"),
    ("pandas",          "pandas"),
    ("pandas_ta",       "pandas_ta"),
    ("flask",           "flask"),
    ("python-dotenv",   "dotenv"),
    ("google-genai",    "google.genai"),
    ("groq",            "groq"),
    ("schedule",        "schedule"),
    ("matplotlib",      "matplotlib"),
    ("requests",        "requests"),
]
manquantes = []
for nom, mod in deps:
    try:
        __import__(mod)
        check(nom, OK)
    except ImportError:
        manquantes.append(nom)
        check(nom, KO, "import échoue")
if manquantes:
    check("→ Pour tout réinstaller", WARN, f"{len(manquantes)} dep(s) manquante(s)",
          "/Users/ruby-rosa/miniconda3/bin/pip install -r requirements.txt")

# ── 4. Clés API (.env) ──────────────────────────────────────────────────
hdr("Clés API (.env)")
try:
    from dotenv import load_dotenv
    load_dotenv()
    env_loaded = True
except ImportError:
    env_loaded = False
    check("python-dotenv", KO, "absent",
          "/Users/ruby-rosa/miniconda3/bin/pip install python-dotenv")

if env_loaded:
    if Path(".env").exists():
        check(".env présent", OK, f"{Path('.env').stat().st_size} octets")
    else:
        check(".env", KO, "fichier manquant",
              "Restaure depuis le backup : "
              "cp ~/Desktop/alphasignal_backup_*/. env ./.env (sans espace)")

    for key in ("GEMINI_API_KEY", "GROQ_API_KEY",
                "EMAIL_SENDER", "EMAIL_APP_PASSWORD",
                "NEWSAPI_KEY", "ALPHA_VANTAGE_KEY"):
        val = os.getenv(key, "")
        if val:
            check(key, OK, f"présente ({len(val)} chars)")
        else:
            optional = key in ("NEWSAPI_KEY", "ALPHA_VANTAGE_KEY")
            check(key, WARN if optional else KO,
                  "absente" + (" (optionnelle)" if optional else ""),
                  "" if optional else f"Restaure {key} depuis ~/Desktop/alphasignal_backup_*/.env")

# ── 5. LaunchAgents ─────────────────────────────────────────────────────
hdr("LaunchAgents")
try:
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
    lignes_actives = [l for l in out.stdout.splitlines() if "alphasignal" in l.lower()]
    plists = list(Path.home().glob("Library/LaunchAgents/com.alphasignal.*.plist"))

    if lignes_actives:
        check(f"{len(lignes_actives)} agent(s) chargé(s)", OK)
        for l in lignes_actives:
            label = l.split()[-1] if l.split() else l
            print(f"     • {label}")
    else:
        check("LaunchAgents", KO, "aucun agent AlphaSignal chargé",
              "Recharger tous les agents :\n"
              "   for f in ~/Library/LaunchAgents/com.alphasignal.*.plist; do "
              "launchctl bootstrap gui/$(id -u) \"$f\"; done")
    if plists and not lignes_actives:
        check("plists présents mais inactifs", WARN, f"{len(plists)} fichier(s) trouvé(s)",
              "Voir commande de rechargement ci-dessus")
    elif not plists:
        check("Fichiers plist", KO, "aucun com.alphasignal.*.plist dans ~/Library/LaunchAgents",
              "Réinstaller : bash scripts/install_launchd.sh")
except Exception as e:
    check("launchctl", KO, str(e)[:100])

# ── 6. Base de données ──────────────────────────────────────────────────
hdr("Base de données")
db = ROOT / "data" / "database.db"
if db.exists():
    size_kb = db.stat().st_size // 1024
    check("data/database.db", OK, f"{size_kb} KB")
    try:
        conn = sqlite3.connect(str(db))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        # Compte les tables (sanity)
        nb_tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        if result and result[0] == "ok":
            check("PRAGMA integrity_check", OK, f"intégrité OK ({nb_tables} tables)")
        else:
            check("PRAGMA integrity_check", KO, str(result),
                  "Restaurer la BDD depuis le backup : "
                  "cp ~/Desktop/alphasignal_backup_*/database.db data/database.db")
    except Exception as e:
        check("Lecture sqlite", KO, str(e)[:100],
              "cp ~/Desktop/alphasignal_backup_*/database.db data/database.db")
else:
    check("data/database.db", KO, "fichier introuvable",
          "cp ~/Desktop/alphasignal_backup_*/database.db data/database.db")

# ── 7. Énergie / anti-veille ────────────────────────────────────────────
hdr("Énergie & anti-veille (pmset)")
try:
    out = subprocess.run(["pmset", "-g"], capture_output=True, text=True, timeout=5)
    lignes = {l.split()[0]: l.strip() for l in out.stdout.splitlines() if l.strip().split()}

    sleep = lignes.get("sleep", "")
    disksleep = lignes.get("disksleep", "")
    if "sleep" in lignes:
        # sleep 0 = jamais ; sinon en minutes
        val = sleep.split()[1] if len(sleep.split()) > 1 else "?"
        if val == "0":
            check("Veille système", OK, "désactivée (sleep=0)")
        else:
            check("Veille système", WARN, f"activée ({sleep})",
                  "Pour empêcher la veille (utile pour les cycles) : "
                  "sudo pmset -a sleep 0 disksleep 0")
    if disksleep:
        check("Veille disque", OK if "0" in disksleep.split() else WARN, disksleep)

    sched = subprocess.run(["pmset", "-g", "sched"],
                            capture_output=True, text=True, timeout=5)
    if "No scheduled events" in sched.stdout or not sched.stdout.strip():
        check("Wake schedule", WARN, "aucun wake programmé",
              "Pour réveiller le Mac chaque matin à 7h25 : "
              "sudo pmset repeat wakeorpoweron MTWRFSU 07:25:00")
    else:
        first_line = next((l for l in sched.stdout.splitlines() if l.strip()), "")
        check("Wake schedule", OK, first_line.strip()[:80])
except Exception as e:
    check("pmset", KO, str(e)[:100], "Vérifier outil pmset")

# ── 8. Backup le plus récent ────────────────────────────────────────────
hdr("Backup le plus récent")
backups = sorted(Path.home().glob("Desktop/alphasignal_backup_*"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
if backups:
    last = backups[0]
    check(f"backup trouvé", OK, str(last))
    # Compare la version Python si possible
    pyinfo = last / "python_info.txt"
    if pyinfo.exists():
        try:
            saved = pyinfo.read_text()
            for line in saved.splitlines():
                if line.startswith("Version"):
                    if v in line:
                        check("Version Python identique au backup", OK, line.strip())
                    else:
                        check("Version Python a changé", WARN,
                              f"backup: {line.strip()} | maintenant: {v}",
                              "/Users/ruby-rosa/miniconda3/bin/pip install -r requirements.txt --force-reinstall")
                    break
        except Exception:
            pass
else:
    check("Aucun backup trouvé", WARN, "lance d'abord scripts/backup_before_update.sh")

# ── 9. Récap ────────────────────────────────────────────────────────────
print("\n" + "━" * 60)
print("RÉCAP")
print("━" * 60)
oks   = sum(1 for _, e, _, _ in results if e == OK)
warns = sum(1 for _, e, _, _ in results if e == WARN)
kos   = sum(1 for _, e, _, _ in results if e == KO)
print(f"  ✅ {oks} OK   ⚠️  {warns} warnings   ❌ {kos} échecs")

if kos > 0 or warns > 0:
    print("\n━━ À RÉPARER ━━")
    for label, etat, detail, repair in results:
        if etat in (KO, WARN) and repair:
            print(f"\n{etat} {label}")
            if detail:
                print(f"   ({detail})")
            print(f"   → {repair}")

sys.exit(0 if kos == 0 else 1)
