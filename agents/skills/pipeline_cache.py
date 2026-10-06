"""
agents/skills/pipeline_cache.py — Pipeline groupé : une analyse par actif, action et jour (Phase 4 / Q2).

- Cache des résultats RÉUSSIS uniquement (table pipeline_cache, clé ticker + jour
  de Lisbonne + action BUY/SELL), partagé entre les processus des cycles. Un
  résultat en cache redonne le même coefficient de taille, sans appel LLM ni
  nouvelle entrée dans metacognition_log. Si l'action change, nouvelle analyse.
- Sans cache et pipeline en échec : mode « Prudent », taille ×
  PIPELINE_FALLBACK_FACTOR (le minimum viable du Budget Manager s'applique
  ensuite), fallback journalisé (log + table pipeline_fallbacks), alerte au-delà
  de PIPELINE_FALLBACK_ALERT couples (ticker, action) DISTINCTS en fallback dans
  la journée (heartbeat du tactical, rapport quotidien) : un même actif qui
  échoue à chaque cycle ne déclenche pas l'alerte à lui seul.
- Conseiller réel (origine="conseiller") : ancien comportement, pipeline à chaque
  appel, sans cache ni fallback. Le chat (origine="chat") n'arrive jamais ici (E2).
"""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
from utils.database import get_connection
from utils.logger import get_logger
from agents.skills.pipeline_grouped import executer_pipeline, doit_executer

logger = get_logger(__name__)

_DDL = (
    """CREATE TABLE IF NOT EXISTS pipeline_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        jour TEXT NOT NULL,                       -- AAAA-MM-JJ, jour de Lisbonne
        action TEXT NOT NULL,                     -- BUY | SELL
        taille_factor_ajustement REAL NOT NULL,
        resultat TEXT NOT NULL,                   -- JSON du pipeline réussi
        source TEXT,                              -- gemini | groq
        cree_le TEXT NOT NULL,                    -- UTC ISO
        UNIQUE (ticker, jour, action))""",
    """CREATE TABLE IF NOT EXISTS pipeline_fallbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        jour TEXT NOT NULL,
        action TEXT NOT NULL,
        horodatage TEXT NOT NULL,                 -- UTC ISO
        raison TEXT,
        facteur REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_fallbacks_jour ON pipeline_fallbacks (jour)",
)


def jour_lisbonne(decalage_jours: int = 0) -> str:
    return (datetime.now(ZoneInfo(config.TIMEZONE)).date() + timedelta(days=decalage_jours)).isoformat()


def _connexion():
    conn = get_connection()
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def lire_cache(ticker: str, jour: str, action: str) -> dict | None:
    conn = _connexion()
    try:
        row = conn.execute("SELECT resultat, taille_factor_ajustement FROM pipeline_cache "
                           "WHERE ticker = ? AND jour = ? AND action = ?", (ticker, jour, action)).fetchone()
    finally:
        conn.close()
    return {**json.loads(row[0]), "taille_factor_ajustement": row[1]} if row else None


def ecrire_cache(ticker: str, jour: str, action: str, pipeline: dict) -> None:
    """Premier résultat réussi du jour conservé (INSERT OR IGNORE : processus concurrents)."""
    conn = _connexion()
    try:
        conn.execute("INSERT OR IGNORE INTO pipeline_cache (ticker, jour, action, taille_factor_ajustement, "
                     "resultat, source, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (ticker, jour, action, float(pipeline.get("taille_factor_ajustement", 1.0)),
                      json.dumps(pipeline, ensure_ascii=False, default=str), pipeline.get("source"),
                      datetime.now(timezone.utc).isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def noter_fallback(ticker: str, jour: str, action: str, raison: str, facteur: float) -> None:
    logger.warning(f"Pipeline {ticker} ({action}) en échec — mode Prudent ×{facteur} (raison : {raison})")
    conn = _connexion()
    try:
        conn.execute("INSERT INTO pipeline_fallbacks (ticker, jour, action, horodatage, raison, facteur) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (ticker, jour, action,
                     datetime.now(timezone.utc).isoformat(timespec="seconds"), raison[:200], facteur))
        conn.commit()
    finally:
        conn.close()


def compter_fallbacks(jour: str) -> tuple[int, int]:
    """(couples (ticker, action) distincts en fallback, total des fallbacks) du jour."""
    conn = _connexion()
    try:
        return tuple(conn.execute("SELECT COUNT(DISTINCT ticker || '|' || action), COUNT(*) "
                                  "FROM pipeline_fallbacks WHERE jour = ?", (jour,)).fetchone())
    finally:
        conn.close()


def etat_fallbacks() -> dict:
    """Pour le heartbeat du tactical : alerte sur les couples distincts, total pour information."""
    couples, total = compter_fallbacks(jour_lisbonne())
    alerte = (f"Pipeline : {couples} couples (ticker, action) en mode Prudent aujourd'hui "
              f"({total} fallbacks), seuil {config.PIPELINE_FALLBACK_ALERT}"
              if couples > config.PIPELINE_FALLBACK_ALERT else None)
    return {"pipeline_fallbacks_couples_jour": couples, "pipeline_fallbacks_jour": total,
            "alerte_pipeline": alerte}


def section_rapport() -> str:
    """Bloc du rapport quotidien, seulement si aujourd'hui ou hier dépasse le seuil (couples distincts)."""
    seuil = config.PIPELINE_FALLBACK_ALERT
    (c_auj, t_auj), (c_hier, t_hier) = compter_fallbacks(jour_lisbonne()), compter_fallbacks(jour_lisbonne(-1))
    if c_auj <= seuil and c_hier <= seuil:
        return ""
    return (f"\n## ⚠️ Pipeline en mode Prudent\n\n"
            f"- Aujourd'hui (depuis 00h00) : {c_auj} couple(s) (ticker, action) en fallback, "
            f"{t_auj} fallback(s) au total — seuil {seuil} couples\n"
            f"- Hier : {c_hier} couple(s), {t_hier} fallback(s)\n"
            f"- En mode Prudent, la taille est multipliée par {config.PIPELINE_FALLBACK_FACTOR}.\n")


def purger(jours_cache: int = 7, jours_fallbacks: int = 30) -> tuple[int, int]:
    """Rétention (cycle cleanup) : seul le cache du jour sert, l'historique des fallbacks garde 30 j."""
    conn = _connexion()
    try:
        a = conn.execute("DELETE FROM pipeline_cache WHERE jour < ?", (jour_lisbonne(-jours_cache),)).rowcount
        b = conn.execute("DELETE FROM pipeline_fallbacks WHERE jour < ?", (jour_lisbonne(-jours_fallbacks),)).rowcount
        conn.commit()
        return a, b
    finally:
        conn.close()


def executer_pipeline_cache(ticker: str, analyses: dict, resultat: dict,
                            regime: str | None = None, origine: str = "cycle") -> dict:
    """Remplace executer_pipeline dans decider() : cache du jour, sinon pipeline, sinon mode Prudent."""
    if origine != "cycle" or not doit_executer(resultat):
        return executer_pipeline(ticker, analyses, resultat, regime=regime)  # conseiller / pipeline sauté
    action, jour = resultat["decision"], jour_lisbonne()
    try:
        cache = lire_cache(ticker, jour, action)
    except Exception as e:
        logger.warning(f"Cache pipeline {ticker} illisible : {e}")
        cache = None
    if cache:
        return {**cache, "cache": True,
                "raisons_ajustement": cache.get("raisons_ajustement", []) + ["cache du jour"]}

    pipeline = executer_pipeline(ticker, analyses, resultat, regime=regime)
    if pipeline.get("executed"):
        try:
            ecrire_cache(ticker, jour, action, pipeline)
        except Exception as e:
            logger.warning(f"Cache pipeline {ticker} non écrit : {e}")
        return pipeline

    facteur, raison = config.PIPELINE_FALLBACK_FACTOR, str(pipeline.get("raison") or "?")
    try:
        noter_fallback(ticker, jour, action, raison, facteur)
    except Exception as e:
        logger.warning(f"Fallback pipeline {ticker} non enregistré : {e}")
    return {**pipeline, "fallback": True, "taille_factor_ajustement": facteur,
            "raisons_ajustement": [f"Pipeline indisponible ({raison[:60]}) : mode Prudent ×{facteur}"]}
