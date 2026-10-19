"""
agents/paper_trader/anti_boucle.py — Garde-fou anti-boucle (REGISTRE_CRITERES v1.8, §9.4).

Après une fermeture automatique (stop ou objectif : CLOSED_SL, CLOSED_TP, et CLOSED_TRAILING, qui est
un stop), aucune réouverture paper du même actif pendant 24 h : refus « anti_boucle ».
Les autres fermetures (signal inverse, manuelle) ne bloquent pas.
"""

from datetime import datetime, timedelta, timezone

from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

MOTIF = "anti_boucle"
DELAI = timedelta(hours=24)
STATUTS_AUTO = ("CLOSED_SL", "CLOSED_TP", "CLOSED_TRAILING")


def fermeture_auto_recente(ticker: str, maintenant: datetime | None = None) -> datetime | None:
    """Date de la dernière fermeture automatique de l'actif si elle a moins de 24 h, sinon None.
    En cas d'erreur de lecture, None (l'ouverture suit alors les autres règles) et un avertissement."""
    try:
        conn = get_connection()
        row = conn.execute(f"SELECT exit_date FROM positions WHERE ticker = ? AND exit_date IS NOT NULL "
                           f"AND status IN ({', '.join('?' * len(STATUTS_AUTO))}) ORDER BY exit_date DESC LIMIT 1",
                           (ticker, *STATUTS_AUTO)).fetchone()
        conn.close()
    except Exception as e:
        logger.warning(f"Anti-boucle {ticker} : lecture impossible ({e})")
        return None
    if not row:
        return None
    fin = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    fin = fin if fin.tzinfo else fin.replace(tzinfo=timezone.utc)
    return fin if (maintenant or datetime.now(timezone.utc)) - fin < DELAI else None
