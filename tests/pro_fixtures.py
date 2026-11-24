"""
tests/pro_fixtures.py — Grand livre et base de l'agent fabriqués pour les tests du dashboard
professionnel (dashboard/pro/).

Deux comptes, jamais mélangés : « Revolut » (réel) et « Paper agent » (paper). La base de l'agent
est créée par le code de l'agent lui-même (tables prices et positions), puis remplie de cours
inventés. Tout est fictif (tickers AAA, BBB…), dans un dossier temporaire : jamais data/, aucun
réseau, aucun .env. Jour de lecture des tests : AUJOURD_HUI.
"""

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import ledger
from tests.socle_fixtures import BaseLedger
from tests.socle_paper_fixtures import creer_base, executer
from utils import database

AUJOURD_HUI = date(2026, 11, 10)
TAUX = "1.25"  # dollars pour un euro, tous les jours du scénario


def quand(mois: int, jour: int, heure: int = 10) -> datetime:
    return datetime(2026, mois, jour, heure, tzinfo=timezone.utc)


def empreinte(chemin: str) -> str:
    with open(chemin, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class BasePro(BaseLedger):
    """Grand livre neuf (self.conn, self.chemin_ledger) et base de l'agent neuve (self.base)."""

    def setUp(self):
        super().setUp()
        self.chemin_ledger = os.path.join(self.dossier.name, "ledger.db")
        self.base = os.path.join(self.dossier.name, "database.db")
        creer_base(self.base)  # positions, avec la colonne « boucle »
        with mock.patch.object(database, "DB_PATH", self.base):
            database.initialiser_base()  # prices
        self._refs = 0

    def ref(self) -> str:
        self._refs += 1
        return f"r{self._refs}"

    def ordre(self, compte_id, symbole, sens, q, prix, le, devise="USD", frais=None, stop=None):
        return ledger.enregistrer_trade(
            self.conn, compte_id=compte_id, instrument_id=ledger.instrument(self.conn, symbole, devise),
            horodatage=le, sens=sens, quantite=q, prix=prix, devise=devise, source="test",
            ref_source=self.ref(), couts=[("commission", frais)] if frais else (),
            contexte={"bras": "regles", "stop_initial": stop} if stop else None)

    def mouvement(self, compte_id, type_, montant, le, devise="EUR", symbole=None):
        return ledger.enregistrer_mouvement(
            self.conn, compte_id=compte_id, horodatage=le, type_=type_, montant=montant, devise=devise,
            source="test", ref_source=self.ref(),
            instrument_id=ledger.instrument(self.conn, symbole, devise) if symbole else None)

    def taux(self, debut=date(2026, 10, 1), fin=AUJOURD_HUI, valeur=TAUX):
        jour = debut
        while jour <= fin:
            ledger.enregistrer_taux(self.conn, jour, valeur, "test")
            jour += timedelta(days=1)
        self.conn.commit()

    def cours(self, ticker, cloture, horodatage="2026-11-09 00:00:00", timeframe="1d"):
        executer(self.base, "INSERT INTO prices (ticker, timeframe, timestamp, close) VALUES (?, ?, ?, ?)",
                 (ticker, timeframe, horodatage, cloture))

    def compte_reel(self) -> int:
        """Deux trades clos (+98 $ et −20,50 $ nets), deux positions ouvertes, trois mouvements."""
        c = ledger.compte(self.conn, "Revolut", "reel", "EUR")
        self.ordre(c, "AAA", "achat", "10", "100", quand(11, 2), frais="1")
        self.ordre(c, "AAA", "vente", "10", "110", quand(11, 5), frais="1")
        self.ordre(c, "BBB", "achat", "4", "50", quand(11, 3), frais="0.5")
        self.ordre(c, "BBB", "vente", "4", "45", quand(11, 6))
        self.ordre(c, "CCC", "achat", "2", "200", quand(11, 4), frais="2")
        self.ordre(c, "DDD.PA", "achat", "5", "20", quand(11, 5), devise="EUR")
        self.mouvement(c, "depot", "1000", quand(11, 1))
        self.mouvement(c, "retrait", "100", quand(11, 7))
        self.mouvement(c, "dividende", "1.5", quand(11, 6), devise="USD", symbole="AAA")
        self.conn.commit()
        self.cours("CCC", 210.0)  # DDD.PA : aucun cours
        return c

    def compte_paper(self) -> int:
        """Un trade avant le correctif du prix d'entrée (−10 $, −0,5 R), un après (+20 $, +2 R),
        une vente à découvert encore ouverte."""
        c = ledger.compte(self.conn, "Paper agent", "paper", "EUR")
        self.ordre(c, "EEE", "achat", "2", "100", quand(10, 1), stop="90")
        self.ordre(c, "EEE", "vente", "2", "95", quand(10, 5))
        self.ordre(c, "FFF", "achat", "1", "100", quand(10, 25), stop="90")
        self.ordre(c, "FFF", "vente", "1", "120", quand(10, 28))
        self.ordre(c, "GGG", "vente", "3", "50", quand(11, 2), stop="55")
        self.conn.commit()
        self.cours("GGG", 47.0)
        return c
