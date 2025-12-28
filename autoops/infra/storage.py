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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_cache (
                cache_key TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_ts REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evals (
                run_id TEXT PRIMARY KEY,
                created_ts REAL NOT NULL,
                report_json TEXT NOT NULL,
                quality_score REAL NOT NULL,
                structure_score REAL NOT NULL,
                cost_score REAL NOT NULL,
                stability_score REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS judge_evals (
                run_id TEXT PRIMARY KEY,
                created_ts REAL NOT NULL,
                report_json TEXT NOT NULL,
                judge_model TEXT NOT NULL,
                overall REAL NOT NULL,
                correctness REAL NOT NULL,
                completeness REAL NOT NULL,
                concision REAL NOT NULL,
                clarity REAL NOT NULL,
                safety REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            )
            """
        )


def save_judge_eval(run_id: str, report: Dict[str, Any]) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO judge_evals
            (run_id, created_ts, report_json, judge_model, overall, correctness, completeness, concision, clarity, safety)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                time.time(),
                json.dumps(report, ensure_ascii=False),
                report["judge_model"],
                float(report["overall"]),
                float(report["correctness"]),
                float(report["completeness"]),
                float(report["concision"]),
                float(report["clarity"]),
                float(report["safety"]),
            ),
        )
        conn.commit()


def load_judge_eval(run_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT report_json FROM judge_evals WHERE run_id = ?", (run_id,)).fetchone()
    return json.loads(row["report_json"]) if row else None

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


def save_eval(run_id: str, report: Dict[str, Any]) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO evals
            (run_id, created_ts, report_json, quality_score, structure_score, cost_score, stability_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                time.time(),
                json.dumps(report, ensure_ascii=False),
                float(report["quality_score"]),
                float(report["structure_score"]),
                float(report["cost_score"]),
                float(report["stability_score"]),
            ),
        )
        conn.commit()


def load_eval(run_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT report_json FROM evals WHERE run_id = ?", (run_id,)
        ).fetchone()
    return json.loads(row["report_json"]) if row else None


import hashlib


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def make_cache_key(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Reason:
    - Tool cache must be deterministic across runs.
    Benefit:
    - Same tool+args -> same cache key.
    """
    payload = tool_name + ":" + _stable_json(args)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_tool_result(
    tool_name: str, args: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    init_db()
    cache_key = make_cache_key(tool_name, args)
    with _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM tool_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["result_json"])


def set_cached_tool_result(
    tool_name: str, args: Dict[str, Any], result: Dict[str, Any]
) -> None:
    init_db()
    cache_key = make_cache_key(tool_name, args)
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO tool_cache
            (cache_key, tool_name, args_json, result_json, created_ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                tool_name,
                _stable_json(args),
                _stable_json(result),
                time.time(),
            ),
        )
        conn.commit()
