from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "ctc.db"
LEGACY_HISTORY = ROOT / ".ctc_history.json"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS wallet_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                local_date TEXT,
                futures_equity REAL NOT NULL DEFAULT 0,
                overview_balance REAL NOT NULL DEFAULT 0,
                known_wallet_usdt REAL NOT NULL DEFAULT 0,
                estimated_untracked_usdt REAL NOT NULL DEFAULT 0,
                planning_usdt REAL NOT NULL,
                fx_rate REAL NOT NULL DEFAULT 0,
                planning_idr REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT 'refresh',
                plan_id TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_wallet_ts ON wallet_snapshots(ts);
            CREATE INDEX IF NOT EXISTS idx_wallet_plan ON wallet_snapshots(plan_id, ts);

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                plan_id TEXT NOT NULL DEFAULT '',
                lead TEXT NOT NULL,
                raw_signal TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry REAL NOT NULL,
                entry_low REAL,
                entry_high REAL,
                stop_loss REAL NOT NULL,
                leverage REAL NOT NULL,
                leverage_source TEXT,
                futures_equity REAL NOT NULL DEFAULT 0,
                overview_equity REAL NOT NULL DEFAULT 0,
                effective_risk_pct REAL NOT NULL DEFAULT 0,
                max_planned_loss REAL NOT NULL DEFAULT 0,
                recommended_notional REAL NOT NULL DEFAULT 0,
                required_margin REAL NOT NULL DEFAULT 0,
                stop_distance_pct REAL NOT NULL DEFAULT 0,
                target_pressure REAL NOT NULL DEFAULT 0,
                drawdown_pct REAL NOT NULL DEFAULT 0,
                open_risk_pct REAL NOT NULL DEFAULT 0,
                volatility_regime TEXT,
                atr_pct REAL,
                partial_profile TEXT,
                runner_fraction REAL NOT NULL DEFAULT 0,
                weighted_r REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open'
            );
            CREATE INDEX IF NOT EXISTS idx_trades_lead ON trades(lead, created_at);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol, created_at);

            CREATE TABLE IF NOT EXISTS trade_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
                target_no INTEGER NOT NULL,
                price REAL NOT NULL,
                allocation REAL NOT NULL DEFAULT 0,
                r_multiple REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_trade_targets_trade ON trade_targets(trade_id, target_no);
            """
        )
    migrate_legacy_history_once()


def migrate_legacy_history_once() -> int:
    if not LEGACY_HISTORY.exists():
        return 0
    try:
        rows = json.loads(LEGACY_HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(rows, list) or not rows:
        return 0
    with connect() as con:
        count = con.execute("SELECT COUNT(*) FROM wallet_snapshots").fetchone()[0]
        if count:
            return 0
        inserted = 0
        for row in rows:
            planning = float(row.get("planning_usdt", 0) or 0)
            if planning <= 0:
                continue
            con.execute(
                """
                INSERT INTO wallet_snapshots
                (ts, local_date, futures_equity, overview_balance, known_wallet_usdt,
                 estimated_untracked_usdt, planning_usdt, fx_rate, planning_idr, reason, plan_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("ts", "")), str(row.get("local_date", "")),
                    float(row.get("futures_equity", 0) or 0),
                    float(row.get("overview_balance", row.get("copy_balance", 0)) or 0),
                    float(row.get("known_wallet_usdt", 0) or 0),
                    float(row.get("estimated_untracked_usdt", 0) or 0), planning,
                    float(row.get("fx_rate", 0) or 0), float(row.get("planning_idr", 0) or 0),
                    str(row.get("reason", "legacy")), str(row.get("plan_id", "")),
                ),
            )
            inserted += 1
        return inserted


def latest_wallet_snapshot() -> dict[str, Any] | None:
    with connect() as con:
        row = con.execute("SELECT * FROM wallet_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def insert_wallet_snapshot(row: dict[str, Any]) -> int:
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO wallet_snapshots
            (ts, local_date, futures_equity, overview_balance, known_wallet_usdt,
             estimated_untracked_usdt, planning_usdt, fx_rate, planning_idr, reason, plan_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["ts"], row.get("local_date", ""), row.get("futures_equity", 0),
                row.get("overview_balance", 0), row.get("known_wallet_usdt", 0),
                row.get("estimated_untracked_usdt", 0), row["planning_usdt"],
                row.get("fx_rate", 0), row.get("planning_idr", 0),
                row.get("reason", "refresh"), row.get("plan_id", ""),
            ),
        )
        return int(cur.lastrowid)


def list_wallet_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM wallet_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_wallet_snapshots() -> None:
    with connect() as con:
        con.execute("DELETE FROM wallet_snapshots")


def insert_trade(payload: dict[str, Any]) -> int:
    signal = payload["signal"]
    result = payload["result"]
    volatility = result.get("volatility") or {}
    partial = result.get("partial") or {}
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO trades
            (created_at, plan_id, lead, raw_signal, symbol, side, entry, entry_low, entry_high,
             stop_loss, leverage, leverage_source, futures_equity, overview_equity,
             effective_risk_pct, max_planned_loss, recommended_notional, required_margin,
             stop_distance_pct, target_pressure, drawdown_pct, open_risk_pct,
             volatility_regime, atr_pct, partial_profile, runner_fraction, weighted_r, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            (
                payload["created_at"], payload.get("plan_id", ""), payload["lead"],
                payload.get("raw_signal", ""), signal["symbol"], signal["side"],
                float(signal["entry"]), float(signal.get("entry_low", signal["entry"])),
                float(signal.get("entry_high", signal["entry"])), float(signal["stop_loss"]),
                float(signal.get("leverage", 10)), str(signal.get("leverage_source", "")),
                float(payload.get("futures_equity", 0)), float(payload.get("overview_equity", 0)),
                float(result.get("effective_risk_pct", 0)), float(result.get("max_planned_loss", 0)),
                float(result.get("recommended_notional", 0)), float(result.get("required_margin", 0)),
                float(result.get("stop_distance_pct", 0)), float(result.get("target_pressure", 0)),
                float(payload.get("drawdown_pct", 0)), float(payload.get("open_risk_pct", 0)),
                str(volatility.get("regime", "")),
                float(volatility.get("atr_pct")) if volatility.get("atr_pct") is not None else None,
                str(partial.get("profile", "")), float(partial.get("runner_fraction", 0)),
                float(partial.get("weighted_r", 0)),
            ),
        )
        trade_id = int(cur.lastrowid)
        for i, target in enumerate(partial.get("targets") or [], start=1):
            con.execute(
                "INSERT INTO trade_targets (trade_id, target_no, price, allocation, r_multiple) VALUES (?, ?, ?, ?, ?)",
                (trade_id, i, float(target["price"]), float(target.get("fraction", 0)), float(target.get("r_multiple", 0))),
            )
        return trade_id


def list_trades(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    with connect() as con:
        rows = con.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            targets = con.execute(
                "SELECT target_no, price, allocation, r_multiple FROM trade_targets WHERE trade_id=? ORDER BY target_no",
                (row["id"],),
            ).fetchall()
            item["targets"] = [dict(t) for t in targets]
            output.append(item)
        return output
