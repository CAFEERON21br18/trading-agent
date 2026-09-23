"""
scripts/check_health.py — Diagnostic manuel d'AlphaSignal
Usage : python scripts/check_health.py
Vérifie : scheduler, dernier rapport, heartbeat, SMTP, accès APIs.
"""

import sys
import os
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.heartbeat import evaluer_sante, lire_heartbeat

DOSSIER_RAPPORTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "daily",
)


def _ok(msg): print(f"  ✅ {msg}")
def _ko(msg): print(f"  ❌ {msg}")
def _wn(msg): print(f"  ⚠️  {msg}")


def check_scheduler() -> bool:
    """Vérifie que le scheduler de l'OS connaît bien les tâches AlphaSignal."""
    if sys.platform == "win32":
        return _check_scheduler_windows()
    return _check_scheduler_launchd()


def _check_scheduler_launchd() -> bool:
    """Vérifie que launchd connaît bien le job (macOS)."""
    print("\n[1] Scheduler launchd")
    try:
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        if "com.alphasignal.daily" in result.stdout:
            ligne = next(l for l in result.stdout.splitlines() if "com.alphasignal.daily" in l)
            _ok(f"Job chargé : {ligne.strip()}")
            return True
        _ko("Job 'com.alphasignal.daily' non chargé dans launchctl")
        print("     → relance : bash scripts/install_launchd.sh")
        return False
    except Exception as e:
        _ko(f"Impossible de vérifier launchctl : {e}")
        return False


def _check_scheduler_windows() -> bool:
    """Vérifie les 7 tâches AlphaSignal dans le Planificateur de tâches (Windows)."""
    print("\n[1] Scheduler — Planificateur de tâches Windows")
    from utils.scheduler_check import verifier_taches_windows
    ok, details, manquantes, echecs = verifier_taches_windows()
    for ligne in details:
        print(f"     {ligne}")
    if manquantes:
        _ko(f"Tâches manquantes : {', '.join(manquantes)}")
    if echecs:
        _ko(f"Tâches en échec : {', '.join(echecs)}")
    if ok:
        _ok("Les 7 tâches sont présentes et saines")
    return ok


def check_dernier_rapport() -> bool:
    """Vérifie qu'un rapport récent existe."""
    print("\n[2] Dernier rapport quotidien")
    if not os.path.isdir(DOSSIER_RAPPORTS):
        _ko(f"Dossier inexistant : {DOSSIER_RAPPORTS}")
        return False
    rapports = sorted(f for f in os.listdir(DOSSIER_RAPPORTS) if f.startswith("report_"))
    if not rapports:
        _ko("Aucun rapport généré")
        return False
    dernier = rapports[-1]
    chemin = os.path.join(DOSSIER_RAPPORTS, dernier)
    age_heures = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(chemin))).total_seconds() / 3600
    if age_heures < 26:
        _ok(f"{dernier} (il y a {age_heures:.1f}h)")
        return True
    _wn(f"{dernier} a {age_heures:.1f}h — > 26h, scheduler probablement bloqué")
    return False


def check_heartbeat() -> bool:
    """Vérifie le heartbeat."""
    print("\n[3] Heartbeat")
    sante = evaluer_sante()
    hb = lire_heartbeat()
    if not hb:
        _wn("Aucun heartbeat — la routine n'a pas tourné depuis l'upgrade")
        return False
    print(f"     Dernier run réussi : {hb.get('last_successful_run', 'N/A')}")
    print(f"     Échecs consécutifs : {hb.get('consecutive_failures', 0)}")
    print(f"     Statut             : {sante['status']}")
    if sante["ok"]:
        _ok(f"Système sain ({sante['heures_depuis_dernier_run']:.1f}h depuis dernier run)")
        return True
    _ko(sante["raison"])
    return False


def check_smtp() -> bool:
    """Test connexion SMTP (sans envoyer d'email)."""
    print("\n[4] Connexion SMTP Gmail")
    import smtplib, ssl
    if not config.EMAIL_APP_PASSWORD:
        _ko("EMAIL_APP_PASSWORD vide dans .env")
        return False
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as srv:
            srv.starttls(context=ctx)
            srv.login(config.EMAIL_SENDER, config.EMAIL_APP_PASSWORD)
        _ok(f"Auth Gmail OK ({config.EMAIL_SENDER})")
        return True
    except Exception as e:
        _ko(f"Échec : {e}")
        return False


def check_apis() -> bool:
    """Test rapide des APIs externes."""
    print("\n[5] APIs de données")
    import requests
    cibles = [
        ("yfinance",      "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d"),
        ("CoinGecko",     "https://api.coingecko.com/api/v3/ping"),
        ("Fear & Greed",  "https://api.alternative.me/fng/?limit=1"),
        ("NewsAPI",       f"https://newsapi.org/v2/top-headlines?country=us&pageSize=1&apiKey={config.NEWSAPI_KEY}" if config.NEWSAPI_KEY else None),
        ("Alpha Vantage", f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey={config.ALPHA_VANTAGE_KEY}" if config.ALPHA_VANTAGE_KEY else None),
    ]
    tout_ok = True
    for nom, url in cibles:
        if url is None:
            _wn(f"{nom} : clé non configurée")
            continue
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                _ok(f"{nom} : {r.status_code}")
            else:
                _wn(f"{nom} : code {r.status_code}")
                tout_ok = False
        except Exception as e:
            _ko(f"{nom} : {e}")
            tout_ok = False
    return tout_ok


def main():
    print("=" * 60)
    print(f"AlphaSignal — Diagnostic santé — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    resultats = [
        check_scheduler(),
        check_dernier_rapport(),
        check_heartbeat(),
        check_smtp(),
        check_apis(),
    ]

    print("\n" + "=" * 60)
    nb_ok = sum(resultats)
    print(f"Résultat : {nb_ok}/{len(resultats)} checks OK")
    print("=" * 60)
    return 0 if all(resultats) else 1


if __name__ == "__main__":
    sys.exit(main())
