"""Schéma du grand livre : tables en écriture seule (ni UPDATE ni DELETE)."""
import sqlite3

TABLES = (
    "comptes", "instruments", "trades", "couts",
    "change", "valeur_quotidienne", "contexte_entree",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS comptes (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('reel', 'paper', 'demo')),
    devise TEXT NOT NULL CHECK (length(devise) = 3),
    cree_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    symbole TEXT NOT NULL UNIQUE,
    nom TEXT,
    classe TEXT NOT NULL DEFAULT 'action',
    devise TEXT NOT NULL CHECK (length(devise) = 3)
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    compte_id INTEGER NOT NULL REFERENCES comptes(id),
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    horodatage TEXT NOT NULL,
    sens TEXT NOT NULL CHECK (sens IN ('achat', 'vente')),
    quantite TEXT NOT NULL,
    prix TEXT NOT NULL,
    devise TEXT NOT NULL CHECK (length(devise) = 3),
    taux_change TEXT,
    source TEXT NOT NULL,
    ref_source TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'valide'
        CHECK (statut IN ('valide', 'annulation')),
    remplace_id INTEGER REFERENCES trades(id),
    saisi_le TEXT NOT NULL,
    UNIQUE (source, ref_source)
);
CREATE TABLE IF NOT EXISTS couts (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES trades(id),
    type TEXT NOT NULL CHECK (type IN
        ('commission', 'spread', 'change', 'financement', 'autre')),
    montant TEXT NOT NULL,
    devise TEXT NOT NULL CHECK (length(devise) = 3)
);
CREATE TABLE IF NOT EXISTS change (
    id INTEGER PRIMARY KEY,
    jour TEXT NOT NULL,
    paire TEXT NOT NULL CHECK (paire = 'EURUSD'),
    taux TEXT NOT NULL,
    source TEXT NOT NULL,
    saisi_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valeur_quotidienne (
    id INTEGER PRIMARY KEY,
    compte_id INTEGER NOT NULL REFERENCES comptes(id),
    jour TEXT NOT NULL,
    valeur TEXT NOT NULL,
    devise TEXT NOT NULL CHECK (length(devise) = 3),
    saisi_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contexte_entree (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER NOT NULL UNIQUE REFERENCES trades(id),
    bras TEXT,
    stop_initial TEXT,
    horizon TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_compte ON trades (compte_id, horodatage);
CREATE INDEX IF NOT EXISTS idx_trades_remplace ON trades (remplace_id);
CREATE INDEX IF NOT EXISTS idx_couts_trade ON couts (trade_id);
"""

_DECLENCHEUR = """
CREATE TRIGGER IF NOT EXISTS {table}_sans_{nom} BEFORE {action} ON {table}
BEGIN
    SELECT RAISE(ABORT, 'grand livre en ecriture seule : {action} interdit');
END;
"""


def ouvrir(chemin: str = "data/ledger.db") -> sqlite3.Connection:
    """Ouvre le grand livre, crée les tables et les protections si besoin."""
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for table in TABLES:
        for action, nom in (("UPDATE", "modif"), ("DELETE", "suppr")):
            conn.executescript(
                _DECLENCHEUR.format(table=table, action=action, nom=nom)
            )
    conn.commit()
    return conn
