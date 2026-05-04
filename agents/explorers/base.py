"""
agents/explorers/base.py — Classe de base partagée par les 7 explorateurs
Chaque explorateur spécialise universe() (liste à scanner) et appliquer_filtres()
(retourne score 1-10 + filters_triggered). La base orchestre le scan et la queue.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
from utils.logger import get_logger
from utils.helpers import charger_watchlist, tous_les_tickers
from utils.heartbeat import update_heartbeat_explorer
from agents.explorers.queue_manager import ajouter_decouverte
from alerts.channels.email_channel import envoyer_email

logger = get_logger(__name__)

# v4.1 : seuils plus permissifs pour générer plus de découvertes
SEUIL_QUEUE       = 4   # avant : 6 — tout ce qui est un peu intéressant entre en queue
SEUIL_EMAIL_FORT  = 7   # avant : 8 — alerte email plus tôt
SEUIL_OBSERVATION = 6   # entre 4 et 6 = en observation, ≥ 6 = candidat sérieux


class ExplorerBase:
    """Classe de base — chaque explorateur la sous-classe."""

    nom = "base"  # à surcharger ("crypto", "stock", "index", etc.)

    def __init__(self):
        self.watchlist_active = set(self._tickers_watchlist())

    def _tickers_watchlist(self) -> list[str]:
        """Liste des tickers déjà dans la watchlist ACTIVE (à exclure du scan)."""
        try:
            return tous_les_tickers(charger_watchlist())
        except Exception:
            return []

    # ── Méthodes à surcharger par chaque explorateur ─────────────────────────

    def universe(self) -> list[str]:
        """Liste des tickers à scanner. À surcharger."""
        raise NotImplementedError

    def appliquer_filtres(self, ticker: str) -> tuple[int, list[str], dict]:
        """
        Retourne (score 1-10, filters_triggered list, details dict) pour un ticker.
        À surcharger.
        """
        raise NotImplementedError

    # ── Logique commune ──────────────────────────────────────────────────────

    def scanner(self, max_actifs: int | None = None) -> dict:
        """
        Scan complet (v4.1 — logging détaillé, heartbeat per explorer).
        Pour chaque ticker → score, ajoute à la queue si ≥ SEUIL_QUEUE, email si ≥ SEUIL_EMAIL_FORT.
        """
        t0 = time.time()
        univers_complet = self.universe()
        if max_actifs:
            univers_complet = univers_complet[:max_actifs]
        univers = [t for t in univers_complet if t not in self.watchlist_active]
        exclus_watchlist = len(univers_complet) - len(univers)

        logger.info(f"{'─' * 60}")
        logger.info(f"🔍 {self.nom.upper()} EXPLORER — scan démarré : {len(univers)} actifs "
                    f"(exclus watchlist : {exclus_watchlist})")

        decouvertes = []
        observations = []
        erreurs = 0
        scores_par_actif = {}

        for ticker in univers:
            try:
                score, filtres, details = self.appliquer_filtres(ticker)
                scores_par_actif[ticker] = score
            except Exception as e:
                erreurs += 1
                logger.warning(f"  ⚠️  {ticker} : {str(e)[:80]}")
                continue

            if score < SEUIL_QUEUE:
                continue

            ajoutee = ajouter_decouverte(self.nom, ticker, score, filtres, details)
            if not ajoutee:
                continue

            entry = {"ticker": ticker, "score": score, "filtres": filtres}
            if score >= SEUIL_OBSERVATION:
                decouvertes.append(entry)
                logger.info(f"  🔥 {ticker} score {score}/10 — {len(filtres)} filtre(s) — {filtres[0] if filtres else ''}")
            else:
                observations.append(entry)
                logger.info(f"  👀 {ticker} score {score}/10 — observation")

            if score >= SEUIL_EMAIL_FORT:
                self._notifier_opportunite(ticker, score, filtres, details)

        duree = time.time() - t0
        logger.info(f"🔍 {self.nom.upper()} EXPLORER — terminé en {duree:.1f}s : "
                    f"{len(decouvertes)} découverte(s), {len(observations)} observation(s), "
                    f"{erreurs} erreur(s)")
        logger.info(f"{'─' * 60}")

        # Mettre à jour le heartbeat de l'explorer
        update_heartbeat_explorer(self.nom, {
            "assets_scanned":      len(univers),
            "assets_in_universe":  len(univers_complet),
            "decouvertes":         len(decouvertes),
            "observations":        len(observations),
            "erreurs":             erreurs,
            "duration_sec":        round(duree, 1),
        })

        return {
            "explorer":      self.nom,
            "scannes":       len(univers),
            "decouvertes":   decouvertes,
            "observations":  observations,
            "erreurs":       erreurs,
            "scan_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _notifier_opportunite(self, ticker: str, score: int,
                              filtres: list[str], details: dict) -> None:
        """Envoie un email si score >= SEUIL_EMAIL_FORT."""
        sujet = f"🔍 [{self.nom.upper()}] Opportunité {ticker} — score {score}/10"
        corps = (f"Découverte d'une opportunité par l'explorateur {self.nom}.\n\n"
                 f"Ticker : {ticker}\nScore : {score}/10\n\n"
                 f"Filtres déclenchés :\n" + "\n".join(f"  • {f}" for f in filtres) + "\n\n"
                 f"Détails : {details}\n\n"
                 f"⚠️ Cette opportunité va être analysée par le Decision Engine.\n"
                 f"Paper trading uniquement.")
        try:
            envoyer_email(sujet, corps)
        except Exception as e:
            logger.error(f"Email opportunité {ticker} échoué : {e}")
