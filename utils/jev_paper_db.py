"""
utils/jev_paper_db.py — Tables du portefeuille fantôme Jev (REGISTRE_CRITERES §8).

- jev_paper_positions : une ligne par position fantôme (achat seulement) ;
- jev_paper_journal   : entrées, sorties, et observations p(acheter) ≥ 0,6 non
  achetées avec leur motif.

Ces tables ne sont lues ni par le moteur, ni par le Budget Manager, ni par le
Paper Trader, ni par le registre, ni par les lectures Q1–Q3, ni par le bilan du
§7. Aucune fonction ici ne touche une table du paper (positions, transactions,
portfolio_snapshots). Pas de commit ici : l'appelant fait un jour = une transaction.
"""

import json
from datetime import datetime, timezone

from utils.database import get_connection

_DDL = (
    """CREATE TABLE IF NOT EXISTS jev_paper_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id INTEGER NOT NULL UNIQUE,   -- jev_observations.id de l'entrée
        ticker TEXT NOT NULL,
        statut TEXT NOT NULL CHECK (statut IN ('OPEN', 'CLOSED')),
        jour_entree TEXT NOT NULL,                -- jour de l'observation (Lisbonne)
        prix_entree REAL NOT NULL,                -- p0 du §7.1 : prix de la ligne
        quantite REAL NOT NULL,
        montant_investi REAL NOT NULL,
        p_acheter REAL,
        conviction_niveau INTEGER,
        facteur REAL,                             -- facteur de conviction (0,2 / 0,5 / 1,0)
        montant_risque REAL,                      -- montant du Risk Manager figé dans l'observation
        mode_bm TEXT,
        barre_sortie TEXT,                        -- date de la 5e barre (J+5 du §7.1)
        jour_sortie TEXT,                         -- jour du cycle qui a passé la sortie
        prix_sortie REAL,
        cout_pct REAL,                            -- aller-retour (§7.1)
        cout_euros REAL,
        pnl_brut REAL,
        pnl_net REAL,
        pnl_pct REAL,                             -- net / montant investi
        horodatage TEXT NOT NULL)""",
    # Jamais deux positions fantômes ouvertes sur le même actif
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jev_paper_ouverte ON jev_paper_positions (ticker) "
    "WHERE statut = 'OPEN'",
    """CREATE TABLE IF NOT EXISTS jev_paper_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        horodatage TEXT NOT NULL,                 -- UTC
        jour TEXT NOT NULL,                       -- jour traité (Lisbonne)
        evenement TEXT NOT NULL CHECK (evenement IN ('entree', 'sortie', 'refus')),
        ticker TEXT NOT NULL,
        observation_id INTEGER,
        position_id INTEGER,
        motif TEXT,                               -- refus : motif du §8.2
        details TEXT)""",                         # JSON : taille, plafonds, sortie
    # Une observation n'est traitée qu'une fois (entrée ou refus)
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jev_paper_obs ON jev_paper_journal (observation_id) "
    "WHERE evenement != 'sortie'",
)


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connexion():
    """Connexion à database.db, tables du fantôme créées si besoin."""
    conn = get_connection()
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def observations_traitees(conn) -> set:
    """Ids des observations déjà passées par le fantôme (entrée ou refus)."""
    rows = conn.execute("SELECT observation_id FROM jev_paper_journal "
                        "WHERE evenement != 'sortie' AND observation_id IS NOT NULL").fetchall()
    return {r[0] for r in rows}


def positions_ouvertes(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM jev_paper_positions WHERE statut = 'OPEN' ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _journal(conn, jour: str, evenement: str, ticker: str, observation_id=None,
             position_id=None, motif=None, details: dict | None = None) -> None:
    conn.execute("INSERT INTO jev_paper_journal (horodatage, jour, evenement, ticker, observation_id, "
                 "position_id, motif, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (_maintenant(), jour, evenement, ticker, observation_id, position_id, motif,
                  json.dumps(details or {}, ensure_ascii=False, default=str)))


def ouvrir(conn, obs: dict, jour: str, entree: dict, details: dict) -> int:
    """Position fantôme OPEN depuis une observation ; entree : montant, quantite, facteur."""
    cur = conn.execute(
        "INSERT INTO jev_paper_positions (observation_id, ticker, statut, jour_entree, prix_entree, "
        "quantite, montant_investi, p_acheter, conviction_niveau, facteur, montant_risque, mode_bm, "
        "horodatage) VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (obs["id"], obs["ticker"], obs["jour"], obs["prix"], entree["quantite"], entree["montant"],
         obs.get("p_acheter"), obs.get("conviction_niveau"), entree["facteur"],
         obs.get("montant_risque"), obs.get("mode_bm"), _maintenant()))
    _journal(conn, jour, "entree", obs["ticker"], obs["id"], cur.lastrowid, details=details)
    return cur.lastrowid


def fermer(conn, position: dict, jour: str, barre: str, prix_sortie: float, resultat: dict) -> None:
    """Sortie à la clôture de la 5e barre ; resultat : cout_pct, cout_euros, pnl_brut, pnl_net, pnl_pct."""
    conn.execute(
        "UPDATE jev_paper_positions SET statut = 'CLOSED', barre_sortie = ?, jour_sortie = ?, "
        "prix_sortie = ?, cout_pct = ?, cout_euros = ?, pnl_brut = ?, pnl_net = ?, pnl_pct = ? "
        "WHERE id = ? AND statut = 'OPEN'",
        (barre, jour, prix_sortie, resultat["cout_pct"], resultat["cout_euros"], resultat["pnl_brut"],
         resultat["pnl_net"], resultat["pnl_pct"], position["id"]))
    _journal(conn, jour, "sortie", position["ticker"], position["observation_id"], position["id"],
             details={"barre": barre, "prix_sortie": prix_sortie, **resultat})


def refuser(conn, obs: dict, jour: str, motif: str, details: dict | None = None) -> None:
    """Observation p(acheter) ≥ 0,6 non achetée, avec son motif (§8.2)."""
    _journal(conn, jour, "refus", obs["ticker"], obs["id"], motif=motif, details=details)
