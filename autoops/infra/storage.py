import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("data") / "autoops.sqlite3"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Reason:
    - Ensure schema exists before saving runs.
    Benefit:
    - Zero-manual setup; works on any machine.
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_ts REAL NOT NULL,
                objective TEXT NOT NULL,
                ok INTEGER NOT NULL,
                iterations INTEGER NOT NULL,
                final_answer TEXT,
                state_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                total_tokens INTEGER,
                total_cost REAL
            )
            """
        )
        conn.commit()


def save_run(
    *,
    run_id: str,
    objective: str,
    ok: bool,
    iterations: int,
    final_answer: Optional[str],
    state: Dict[str, Any],
    steps: List[Dict[str, Any]],
    total_tokens: Optional[int] = None,
    total_cost: Optional[float] = None,
) -> None:
    """
    Reason:
    - Persist full run record for audit/replay/debug.
    Benefit:
    - You can compare runs across prompt versions and code changes.
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs
            (run_id, created_ts, objective, ok, iterations, final_answer, state_json, steps_json, total_tokens, total_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                time.time(),
                objective,
                1 if ok else 0,
                iterations,
                final_answer,
                json.dumps(state, ensure_ascii=False),
                json.dumps(steps, ensure_ascii=False),
                total_tokens,
                total_cost,
            ),
        )
        conn.commit()


def list_runs(limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, created_ts, objective, ok, iterations, total_tokens, total_cost
            FROM runs
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def load_run(run_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None
