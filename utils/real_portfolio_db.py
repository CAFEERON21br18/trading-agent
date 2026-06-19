"""
utils/real_portfolio_db.py — BDD du portefeuille RÉEL (v5.0)
Totalement séparé du paper trading. L'utilisateur saisit manuellement.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialiser_real_db() -> None:
    """Crée les tables real_investments, real_advice_log, real_budget,
    investment_plans, plan_alerts (v5.1) si absentes."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS real_investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                asset_name TEXT,
                holding_type TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                direction TEXT DEFAULT 'LONG',
                entry_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                quantity REAL NOT NULL,
                invested_amount REAL NOT NULL,
                leverage REAL DEFAULT 1,
                target_price REAL,
                stop_loss_mental REAL,
                investment_thesis TEXT,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_date TEXT,
                realized_pnl REAL,
                notes TEXT,
                plan_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ajouter colonne plan_id si la table existait déjà (migration douce)
        try:
            c.execute("ALTER TABLE real_investments ADD COLUMN plan_id INTEGER")
        except Exception:
            pass  # déjà présente
        c.execute("""
            CREATE TABLE IF NOT EXISTS real_advice_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_id INTEGER,
                advice_date TEXT NOT NULL,
                advice_type TEXT,
                recommendation TEXT,
                reasoning TEXT,
                urgency TEXT,
                user_decision TEXT,
                user_decision_date TEXT,
                FOREIGN KEY (investment_id) REFERENCES real_investments(id)
            )
        """)
        # v5.1 : budget réel (une seule ligne, id=1)
        c.execute("""
            CREATE TABLE IF NOT EXISTS real_budget (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_capital REAL NOT NULL,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # v5.1 : plans d'investissement
        c.execute("""
            CREATE TABLE IF NOT EXISTS investment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_type TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_plan_id INTEGER,
                objective TEXT,
                target_return_percent REAL,
                target_amount REAL,
                time_horizon TEXT,
                vision TEXT,
                risk_tolerance TEXT,
                allocated_budget REAL,
                allocated_budget_percent REAL,
                max_position_size REAL,
                rules TEXT,
                status TEXT DEFAULT 'active',
                progress_notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_plan_id) REFERENCES investment_plans(id)
            )
        """)
        # Migration douce v5.2 : ajouter allocated_budget_percent si manquant
        try:
            c.execute("ALTER TABLE investment_plans ADD COLUMN allocated_budget_percent REAL")
        except Exception:
            pass
        # v5.1 : alertes des plans
        c.execute("""
            CREATE TABLE IF NOT EXISTS plan_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                alert_date TEXT NOT NULL,
                alert_type TEXT,
                message TEXT,
                severity TEXT,
                user_response TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plan_id) REFERENCES investment_plans(id)
            )
        """)
        conn.commit()
        conn.close()
        logger.info("BDD portefeuille réel v5.1 initialisée (investments + advice + budget + plans + alerts)")
    except Exception as e:
        logger.error(f"Erreur init real DB : {e}")
        raise


# ── v5.1 : Budget réel ──────────────────────────────────────────────────────

def get_budget_capital() -> float:
    conn = get_connection()
    row = conn.execute("SELECT total_capital FROM real_budget WHERE id=1").fetchone()
    conn.close()
    return float(row["total_capital"]) if row else 0.0


def set_budget_capital(total: float) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO real_budget (id, total_capital, last_updated)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET total_capital=excluded.total_capital,
                                       last_updated=excluded.last_updated
    """, (total, _now_iso()))
    conn.commit()
    conn.close()


def get_real_budget_summary(prix_courants: dict | None = None) -> dict:
    """
    Calcule l'état du budget réel à partir des positions ouvertes.
    Retourne tout (total, invested, available, by_holding, by_instrument, P&L).
    """
    total_capital = get_budget_capital()
    positions = lire_investissements(filtre_status="OPEN")
    invested = sum(p["invested_amount"] for p in positions)
    available = total_capital - invested

    by_holding    = {"actif": 0.0, "passif": 0.0, "moyen": 0.0}
    by_instrument = {"normal": 0.0, "cfd": 0.0, "crypto": 0.0}
    for p in positions:
        h = p.get("holding_type", "moyen")
        i = p.get("instrument_type", "normal")
        by_holding[h]    = by_holding.get(h, 0)    + p["invested_amount"]
        by_instrument[i] = by_instrument.get(i, 0) + p["invested_amount"]

    # Valeur actuelle (avec prix marché)
    if prix_courants is None:
        prix_courants = {}
    current_value = 0.0
    from utils.data_fetcher import prix_actuel
    for p in positions:
        prix = prix_courants.get(p["asset"]) or prix_actuel(p["asset"])
        if prix:
            current_value += p["quantity"] * prix
    unrealized_pnl = current_value - invested if invested else 0.0

    return {
        "total_capital":           total_capital,
        "invested":                invested,
        "available":               available,
        "invested_percent":        round(invested / total_capital * 100, 1) if total_capital else 0,
        "current_value":           current_value,
        "unrealized_pnl":          unrealized_pnl,
        "unrealized_pnl_percent":  round(unrealized_pnl / invested * 100, 1) if invested else 0,
        "by_holding":              by_holding,
        "by_instrument":           by_instrument,
        "positions_count":         len(positions),
    }


# ── CRUD investissements ────────────────────────────────────────────────────

def ajouter_investissement(p: dict) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO real_investments
        (asset, asset_name, holding_type, instrument_type, direction,
         entry_price, entry_date, quantity, invested_amount, leverage,
         target_price, stop_loss_mental, investment_thesis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["asset"], p.get("asset_name"), p["holding_type"], p["instrument_type"],
        p.get("direction", "LONG"), p["entry_price"], p.get("entry_date", _now_iso()),
        p["quantity"], p["invested_amount"], p.get("leverage", 1),
        p.get("target_price"), p.get("stop_loss_mental"), p.get("investment_thesis"),
    ))
    pos_id = c.lastrowid
    conn.commit()
    conn.close()
    return pos_id


def fermer_investissement(inv_id: int, exit_price: float, notes: str = "") -> dict | None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM real_investments WHERE id = ?", (inv_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    inv = dict(row)
    if inv["direction"] == "LONG":
        pnl = (exit_price - inv["entry_price"]) * inv["quantity"]
    else:
        pnl = (inv["entry_price"] - exit_price) * inv["quantity"]
    c.execute("""
        UPDATE real_investments
        SET status='CLOSED', exit_price=?, exit_date=?, realized_pnl=?, notes=?, updated_at=?
        WHERE id=?
    """, (exit_price, _now_iso(), pnl, notes, _now_iso(), inv_id))
    conn.commit()
    conn.close()
    return {"realized_pnl": pnl, "asset": inv["asset"]}


def supprimer_investissement(inv_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM real_investments WHERE id = ?", (inv_id,))
    n = c.rowcount
    c.execute("DELETE FROM real_advice_log WHERE investment_id = ?", (inv_id,))
    conn.commit()
    conn.close()
    return n > 0


def lire_investissements(filtre_status: str | None = None,
                         filtre_holding: str | None = None,
                         filtre_instrument: str | None = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM real_investments"
    conditions, params = [], []
    if filtre_status:
        conditions.append("status = ?")
        params.append(filtre_status)
    if filtre_holding:
        conditions.append("holding_type = ?")
        params.append(filtre_holding)
    if filtre_instrument:
        conditions.append("instrument_type = ?")
        params.append(filtre_instrument)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Conseils ────────────────────────────────────────────────────────────────

def ajouter_conseil(investment_id: int, advice_type: str, recommendation: str,
                    reasoning: str, urgency: str = "moyenne") -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO real_advice_log (investment_id, advice_date, advice_type,
                                     recommendation, reasoning, urgency)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (investment_id, _now_iso(), advice_type, recommendation, reasoning, urgency))
    advice_id = c.lastrowid
    conn.commit()
    conn.close()
    return advice_id


def enregistrer_decision_user(advice_id: int, decision: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE real_advice_log SET user_decision=?, user_decision_date=? WHERE id=?
    """, (decision, _now_iso(), advice_id))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def lire_conseils_actifs() -> list[dict]:
    """Conseils non encore répondus par l'utilisateur."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, i.asset, i.asset_name
        FROM real_advice_log a
        LEFT JOIN real_investments i ON a.investment_id = i.id
        WHERE a.user_decision IS NULL
        ORDER BY a.advice_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resume_portefeuille() -> dict:
    """Stats globales du portefeuille réel."""
    invs = lire_investissements(filtre_status="OPEN")
    invested = sum(i["invested_amount"] for i in invs)
    realized = sum((c["realized_pnl"] or 0) for c in lire_investissements(filtre_status="CLOSED"))
    return {
        "open_count":   len(invs),
        "total_invested": invested,
        "realized_pnl": realized,
    }


# ── v5.1 : Plans d'investissement (CRUD) ────────────────────────────────────

def creer_plan(p: dict) -> int:
    """Crée un plan. Accepte allocated_budget (€) OU allocated_budget_percent (%).
    Le rules peut être dict (sérialisé en JSON) ou string."""
    import json as _json
    rules = p.get("rules")
    if isinstance(rules, (dict, list)):
        rules = _json.dumps(rules, ensure_ascii=False)
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO investment_plans
        (plan_type, name, parent_plan_id, objective, target_return_percent,
         target_amount, time_horizon, vision, risk_tolerance, allocated_budget,
         allocated_budget_percent, max_position_size, rules, status, progress_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p.get("plan_type", "custom"), p["name"], p.get("parent_plan_id"),
        p.get("objective"), p.get("target_return_percent"), p.get("target_amount"),
        p.get("time_horizon"), p.get("vision"), p.get("risk_tolerance"),
        p.get("allocated_budget"), p.get("allocated_budget_percent"),
        p.get("max_position_size"), rules,
        p.get("status", "active"), p.get("progress_notes"),
    ))
    pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid


def _resoudre_budget(plan: dict, capital_total: float) -> dict:
    """
    Calcule allocated_budget en € à partir du % et du capital.
    Pour un plan ENFANT (avec parent_plan_id) : % du budget du parent.
    Pour un plan RACINE : % du capital total.
    Si allocated_budget est déjà en €, on le garde.
    """
    pct = plan.get("allocated_budget_percent")
    if pct is None or pct <= 0:
        return plan  # budget € direct, rien à recalculer
    parent_id = plan.get("parent_plan_id")
    if parent_id:
        parent = lire_plan(parent_id)
        if parent:
            parent_budget = _resoudre_budget(parent, capital_total).get("allocated_budget") or 0
            plan["allocated_budget"] = round(parent_budget * pct / 100, 2)
            return plan
    # Sinon : % du capital total
    plan["allocated_budget"] = round(capital_total * pct / 100, 2)
    return plan


def modifier_plan(plan_id: int, updates: dict) -> bool:
    """Modifie un plan. Seuls les champs présents dans updates sont touchés."""
    allowed = {"name", "objective", "target_return_percent", "target_amount",
               "time_horizon", "vision", "risk_tolerance", "allocated_budget",
               "max_position_size", "rules", "status", "progress_notes"}
    sets, vals = [], []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    sets.append("updated_at=?")
    vals.append(_now_iso())
    vals.append(plan_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE investment_plans SET {', '.join(sets)} WHERE id=?", vals)
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def supprimer_plan(plan_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    # Détache les positions liées (au lieu de les supprimer)
    c.execute("UPDATE real_investments SET plan_id=NULL WHERE plan_id=?", (plan_id,))
    c.execute("DELETE FROM plan_alerts WHERE plan_id=?", (plan_id,))
    c.execute("DELETE FROM investment_plans WHERE id=?", (plan_id,))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def lire_plans() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM investment_plans ORDER BY parent_plan_id NULLS FIRST, created_at"
    ).fetchall()
    conn.close()
    capital = get_budget_capital()
    return [_resoudre_budget(dict(r), capital) for r in rows]


def lire_plan(plan_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM investment_plans WHERE id=?", (plan_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _resoudre_budget(dict(row), get_budget_capital())


def positions_du_plan(plan_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM real_investments WHERE plan_id=? ORDER BY created_at DESC",
        (plan_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rattacher_position_plan(inv_id: int, plan_id: int | None) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE real_investments SET plan_id=? WHERE id=?", (plan_id, inv_id))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def progression_plan(plan_id: int) -> dict:
    """Calcule la progression d'un plan vers son objectif."""
    plan = lire_plan(plan_id)
    if not plan:
        return {"error": "plan introuvable"}
    positions = positions_du_plan(plan_id)
    invested = sum(p["invested_amount"] for p in positions if p["status"] == "OPEN")

    # Valeur actuelle des positions ouvertes
    from utils.data_fetcher import prix_actuel
    valeur_actuelle = 0.0
    for p in positions:
        if p["status"] != "OPEN":
            continue
        prix = prix_actuel(p["asset"])
        if prix:
            valeur_actuelle += p["quantity"] * prix

    # P&L réalisé (positions closes liées au plan)
    pnl_realise = sum((p.get("realized_pnl") or 0) for p in positions if p["status"] == "CLOSED")
    pnl_latent  = valeur_actuelle - invested if invested else 0
    pnl_total   = pnl_realise + pnl_latent

    target_pct = plan.get("target_return_percent") or 0
    budget = plan.get("allocated_budget") or invested or 1
    progression_pct = (pnl_total / budget * 100) if budget else 0

    if target_pct > 0:
        avancement_objectif = (progression_pct / target_pct * 100)
    else:
        avancement_objectif = None

    return {
        "plan_id":             plan_id,
        "invested":            invested,
        "current_value":       valeur_actuelle,
        "pnl_realise":         pnl_realise,
        "pnl_latent":          pnl_latent,
        "pnl_total":           pnl_total,
        "progression_pct":     round(progression_pct, 2),
        "target_pct":          target_pct,
        "avancement_objectif": round(avancement_objectif, 1) if avancement_objectif is not None else None,
        "positions_count":     len([p for p in positions if p["status"] == "OPEN"]),
    }


# ── v5.1 : Alertes de plans ─────────────────────────────────────────────────

def ajouter_alerte_plan(plan_id: int, alert_type: str, message: str,
                        severity: str = "info") -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO plan_alerts (plan_id, alert_date, alert_type, message, severity)
        VALUES (?, ?, ?, ?, ?)
    """, (plan_id, _now_iso(), alert_type, message, severity))
    aid = c.lastrowid
    conn.commit()
    conn.close()
    return aid


def lire_alertes_plans_actives() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, p.name AS plan_name
        FROM plan_alerts a LEFT JOIN investment_plans p ON a.plan_id = p.id
        WHERE a.user_response IS NULL
        ORDER BY a.alert_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def enregistrer_reponse_alerte_plan(alert_id: int, decision: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE plan_alerts SET user_response=? WHERE id=?", (decision, alert_id))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0
