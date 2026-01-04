import json
import datetime as dt
from typing import Any, Dict, List, Optional


def _safe_json_loads(s: Optional[str], default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _fmt_ts(created_ts: Optional[float]) -> str:
    if not created_ts:
        return "UNKNOWN_TIME"
    return dt.datetime.fromtimestamp(float(created_ts)).strftime("%Y-%m-%d %H:%M:%S")


def _extract_tools_from_steps(steps: Any) -> List[str]:
    """
    steps_json is stored by save_run() as json.dumps(steps).
    Based on your earlier logs, each step dict often has tool_name.
    """
    tools: List[str] = []
    if not isinstance(steps, list):
        return tools

    for step in steps:
        if isinstance(step, dict):
            t = step.get("tool_name") or step.get("tool") or step.get("name")
            if isinstance(t, str) and t:
                tools.append(t)
    return tools


def _summarize_tools(tools: List[str], max_items: int = 6) -> str:
    if not tools:
        return "None"
    uniq = []
    seen = set()
    for t in tools:
        if t not in seen:
            uniq.append(t)
            seen.add(t)
    if len(uniq) <= max_items:
        return ", ".join(uniq)
    return ", ".join(uniq[:max_items]) + f", … (+{len(uniq)-max_items} more)"


def build_gate_judge_email(
    *,
    run: Dict[str, Any],
    judge_report: Dict[str, Any],
    thresholds: Dict[str, Any],
    fail_reasons: List[str],
) -> Dict[str, str]:
    """
    Returns {subject, body} for email/slack/webhook reuse.
    Uses your sqlite schema fields from storage.py (no guessing).
    """

    run_id = run["run_id"]
    created = _fmt_ts(run.get("created_ts"))
    objective = (run.get("objective") or "").strip()
    ok = bool(run.get("ok"))
    iterations = run.get("iterations")
    total_tokens = run.get("total_tokens")
    total_cost = float(run.get("total_cost") or 0.0)

    final_answer = (run.get("final_answer") or "").strip()

    state = _safe_json_loads(run.get("state_json"), default={})
    steps = _safe_json_loads(run.get("steps_json"), default=[])
    memory_used = _safe_json_loads(run.get("memory_used_json"), default=[])

    tools = _extract_tools_from_steps(steps)
    tools_summary = _summarize_tools(tools)

    judge_model = judge_report.get("judge_model", "UNKNOWN_JUDGE_MODEL")

    status = "FAIL" if fail_reasons else "PASS"
    subject = f"[autoops-ai] gate_judge {status} run_id={run_id}"

    lines: List[str] = []
    lines.append(f"gate_judge {status}")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Created: {created}")
    lines.append(f"Run OK: {ok} | Iterations: {iterations}")
    if total_tokens is not None:
        lines.append(f"Tokens: {total_tokens}")
    lines.append(f"Cost: ${total_cost:.4f}")
    lines.append("")

    lines.append("Objective:")
    lines.append(objective[:800] if objective else "(empty)")
    lines.append("")

    if final_answer:
        lines.append("Final answer (preview):")
        lines.append(final_answer[:800])
        lines.append("")

    lines.append("Execution summary:")
    lines.append(f"  Steps: {len(steps) if isinstance(steps, list) else 0}")
    lines.append(f"  Tools: {tools_summary}")
    # Optional: show memory_used ids (useful for debugging retrieval)
    if isinstance(memory_used, list) and memory_used:
        lines.append(f"  Memory used: {len(memory_used)}")
        lines.append(
            f"  Memory IDs (preview): {', '.join(memory_used[:5])}"
            + (" …" if len(memory_used) > 5 else "")
        )
    lines.append("")

    lines.append("Judge summary:")
    lines.append(f"  judge_model: {judge_model}")
    for k in [
        "overall",
        "correctness",
        "completeness",
        "concision",
        "clarity",
        "safety",
    ]:
        if k in judge_report:
            lines.append(f"  {k}: {float(judge_report[k]):.3f}")
    lines.append("")

    lines.append("Thresholds:")
    for k, v in thresholds.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    if fail_reasons:
        lines.append("FAIL reasons:")
        for r in fail_reasons:
            lines.append(f"  - {r}")
        lines.append("")
    else:
        lines.append("PASS: all thresholds met")
        lines.append("")

    lines.append("Reproduce:")
    lines.append(f"  python -m autoops.tools.runs show {run_id}")
    lines.append(f"  python -m autoops.tools.runs judge {run_id}")
    lines.append(
        "  python -m autoops.tools.runs gate_judge "
        f"{run_id} --min_overall {thresholds.get('min_overall')} "
        f"--min_correctness {thresholds.get('min_correctness')} "
        f"--min_safety {thresholds.get('min_safety')} "
        f"--max_cost {thresholds.get('max_cost')}"
    )

    return {"subject": subject, "body": "\n".join(lines)}
