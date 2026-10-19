"""
agents/paper_trader/prix_frais.py — Version 2 du mécanisme d'entrée paper (REGISTRE_CRITERES v1.8, §9.4).

À l'ouverture (tactical et quotidien), le prix d'entrée est un prix frais : la dernière barre de
1 minute de Yahoo, si elle a moins de 15 minutes. Le stop, l'objectif et la taille sont recalculés
sur ce prix par le Risk Manager (règles existantes de position_sizer, aucun paramètre changé).
Sans prix frais, pas d'ouverture : refus « prix_frais_indisponible ».
Chaque ouverture enregistre la version du mécanisme (2), le prix de la décision, le prix
d'exécution et son âge en secondes (colonnes ajoutées à `positions` si elles manquent).
Aucun ordre réel : paper trading uniquement.
"""

import math
from datetime import datetime, timedelta, timezone

from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

MECANISME_ENTREE = 2
AGE_MAX_S = 15 * 60   # barre intrajournalière de moins de 15 minutes
DELAI_S = 5           # délai court de la requête Yahoo
MOTIF = "prix_frais_indisponible"
COLONNES = (("mecanisme_entree", "INTEGER"), ("prix_decision", "REAL"),
            ("prix_execution", "REAL"), ("age_prix_s", "REAL"))


def _barres_1min(ticker: str):
    import yfinance as yf
    return yf.Ticker(ticker).history(period="1d", interval="1m", timeout=DELAI_S)


def prix_frais(ticker: str, maintenant: datetime | None = None, telecharger=_barres_1min) -> tuple[float, float] | None:
    """(prix, âge en secondes) de la dernière barre de 1 minute, ou None : requête en échec, pas de
    barre, prix illisible, ou barre de plus de AGE_MAX_S (marché fermé). L'âge part du début de la
    barre, donc il est majoré d'au plus une minute."""
    try:
        hist = telecharger(ticker)
        closes = hist["Close"].dropna() if hist is not None and not hist.empty else None
    except Exception as e:
        logger.warning(f"Prix frais {ticker} : {str(e)[:80]}")
        return None
    if closes is None or closes.empty:
        return None
    prix = float(closes.iloc[-1])
    ts = closes.index[-1].to_pydatetime()
    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    age = ((maintenant or datetime.now(timezone.utc)) - ts).total_seconds()
    if not math.isfinite(prix) or prix <= 0 or age > AGE_MAX_S or age < -timedelta(minutes=2).total_seconds():
        return None
    return prix, max(0.0, age)


def assurer_colonnes(conn) -> None:
    """Ajoute les colonnes de la version 2 à `positions` si elles manquent (même idiome que v5.5.1)."""
    presentes = {r[1] for r in conn.execute("PRAGMA table_info(positions)")}
    for nom, genre in COLONNES:
        if nom not in presentes:
            conn.execute(f"ALTER TABLE positions ADD COLUMN {nom} {genre}")


def enregistrer_entree(pos_id: int, prix_decision: float | None, prix_execution: float, age_s: float) -> bool:
    """Inscrit la version du mécanisme, le prix de la décision, le prix d'exécution et son âge."""
    try:
        conn = get_connection()
        assurer_colonnes(conn)
        conn.execute("UPDATE positions SET mecanisme_entree = ?, prix_decision = ?, prix_execution = ?, "
                     "age_prix_s = ? WHERE id = ?",
                     (MECANISME_ENTREE, prix_decision, prix_execution, round(age_s, 1), pos_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Entrée v{MECANISME_ENTREE} de la position #{pos_id} non enregistrée : {e}")
        return False
