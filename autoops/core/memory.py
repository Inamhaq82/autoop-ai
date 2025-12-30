import json
from typing import Any, Dict, List, Tuple

from autoops.infra.storage import list_runs, load_run


def _tok(s: str) -> set[str]:
    return set((s or "").lower().split())


def jaccard(a: str, b: str) -> float:
    sa = _tok(a)
    sb = _tok(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def find_relevant_runs(objective: str, *, k: int = 3, scan_limit: int = 50) -> List[Dict[str, Any]]:
    """
    Reason:
    - Retrieve prior attempts that look similar to current objective.
    Benefit:
    - Reuse what worked; avoid repeating failures.
    """
    candidates = list_runs(limit=scan_limit)
    scored: List[Tuple[float, str]] = []

    for r in candidates:
        score = jaccard(objective, r.get("objective") or "")
        scored.append((score, r["run_id"]))

    scored.sort(reverse=True, key=lambda x: x[0])

    results: List[Dict[str, Any]] = []
    for score, run_id in scored[:k]:
        run = load_run(run_id)
        if not run:
            continue
        results.append(
            {
                "run_id": run_id,
                "similarity": score,
                "objective": run.get("objective"),
                "ok": bool(run.get("ok")),
                "iterations": run.get("iterations"),
                "final_answer": run.get("final_answer"),
            }
        )
    return results


def format_memories(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return "(none)"
    lines = []
    for m in memories:
        lines.append(
            f"- run_id={m['run_id']} sim={m['similarity']:.3f} ok={m['ok']} iters={m['iterations']} "
            f"objective={str(m['objective'])[:80]!r} "
            f"final={str(m.get('final_answer') or '')[:160]!r}"
        )
    return "\n".join(lines)
