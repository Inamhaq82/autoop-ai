import argparse
import json
import datetime as dt
from typing import Any

from autoops.infra.storage import (
    list_runs,
    load_run,
    save_eval,
    load_eval,
    save_judge_eval,
    load_judge_eval,
)
from autoops.ops.notify import build_gate_judge_email
from autoops.ops.notifiers import EmailNotifier, NullNotifier, load_smtp_config_from_env
from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.tools.text_tools import summarize_text_local
from autoops.core.agent_loop import run_agent_loop
from autoops.core.evaluator import evaluate_run
from autoops.core.judge import judge_run
from autoops.core.memory import find_relevant_runs
from pathlib import Path
import time


def jaccard_similarity(a: str, b: str) -> float:
    sa = set(a.lower().split()) if a else set()
    sb = set(b.lower().split()) if b else set()
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def format_ts(ts: float | None) -> str:
    """Convert unix timestamp -> human readable local time."""
    if not ts:
        return "UNKNOWN_TIME"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def assert_no_duplicate_subcommands(subparsers) -> None:
    """
    Defensive check to avoid regressions from duplicate add_parser calls / alias collisions.
    """
    choices = getattr(subparsers, "choices", {}) or {}
    names = list(choices.keys())

    if len(names) != len(set(names)):
        raise SystemExit(f"Duplicate subcommand names detected: {names}")

    seen = set(names)
    for name, sp in choices.items():
        aliases = getattr(sp, "aliases", []) or []
        for a in aliases:
            if a in seen:
                raise SystemExit(
                    f"Alias collision: '{a}' already registered (while adding '{name}')"
                )
            seen.add(a)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runs.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    p_list = sub.add_parser("list", help="List recent runs")
    p_list.add_argument("--limit", type=int, default=20)

    # show
    p_show = sub.add_parser("show", help="Show a run JSON")
    p_show.add_argument("run_id")

    # compare
    p_cmp = sub.add_parser("compare", help="Compare two runs (basic metrics)")
    p_cmp.add_argument("old_run_id")
    p_cmp.add_argument("new_run_id")

    # eval
    p_eval = sub.add_parser("eval", help="Run heuristic evaluator and save report")
    p_eval.add_argument("run_id")
    p_eval.add_argument("--budget", type=float, default=0.05)

    # compare_eval
    p_ce = sub.add_parser("compare_eval", help="Compare evaluator reports for two runs")
    p_ce.add_argument("old_run_id")
    p_ce.add_argument("new_run_id")

    # gate (evaluator-based regression gate)
    p_gate = sub.add_parser("gate", help="Gate two runs using evaluator deltas")
    p_gate.add_argument("old_run_id")
    p_gate.add_argument("new_run_id")
    p_gate.add_argument("--max_quality_drop", type=float, default=0.10)
    p_gate.add_argument("--max_cost_increase_pct", type=float, default=50.0)

    # judge (LLM-based judge)
    p_judge = sub.add_parser("judge", help="Run LLM judge and save judge report")
    p_judge.add_argument("run_id")
    p_judge.add_argument("--model", type=str, default="gpt-4o-mini")

    # compare_judge
    p_cj = sub.add_parser(
        "compare_judge", help="Compare two judge reports (requires both judged)"
    )
    p_cj.add_argument("old_run_id")
    p_cj.add_argument("new_run_id")

    # gate_judge (judge-based regression gate)
    p_gatej = sub.add_parser(
        "gate_judge", help="Gate a run using judge thresholds + cost threshold"
    )
    p_gatej.add_argument("run_id")

    p_gatej.add_argument(
        "--auto_judge",
        action="store_true",
        help="If judge report is missing, run judge automatically",
    )
    p_gatej.add_argument(
        "--judge_model",
        type=str,
        default="gpt-4o-mini",
        help="Model to use if --auto_judge runs judge",
    )

    # Keep existing canonical flags
    p_gatej.add_argument("--min_overall", type=float, default=0.80)
    p_gatej.add_argument("--min_correctness", type=float, default=0.85)
    p_gatej.add_argument("--min_safety", type=float, default=0.95)
    p_gatej.add_argument("--max_cost", type=float, default=0.05)

    p_gatej.add_argument("--json", action="store_true", help="Print JSON result for CI")

    p_gatej.add_argument(
        "--notify_email",
        type=str,
        default="",
        help="Comma-separated list of emails to notify",
    )
    p_gatej.add_argument(
        "--notify_on",
        choices=["fail", "pass", "always"],
        default="fail",
        help="When to send notifications",
    )
    p_gatej.add_argument(
        "--notify_dry_run",
        action="store_true",
        help="Print notification instead of sending",
    )

    # Add an alias for convenience (what you tried earlier)
    # --min_score behaves like --min_overall
    p_gatej.add_argument(
        "--min_score",
        type=float,
        default=None,
        help="Alias for --min_overall (overrides if provided).",
    )

    # replay
    p_replay = sub.add_parser(
        "replay",
        help="Replay a run's objective. --dry_run prints plan-only with no side effects.",
    )
    p_replay.add_argument("run_id")
    p_replay.add_argument("--dry_run", action="store_true")

    # export
    p_exp = sub.add_parser("export", help="Export a run bundle as one JSON file")
    p_exp.add_argument("run_id")
    p_exp.add_argument(
        "--out",
        type=str,
        default="",
        help="Output path. Default: data/exports/<run_id>.json",
    )
    p_exp.add_argument(
        "--include_raw_json",
        action="store_true",
        help="Include raw *_json string columns in export (larger file)",
    )

    # memory_search
    p_mem = sub.add_parser("memory_search", help="Find similar prior runs by objective")
    p_mem.add_argument("--objective", required=True)
    p_mem.add_argument("--k", type=int, default=3)
    p_mem.add_argument("--scan_limit", type=int, default=50)

    assert_no_duplicate_subcommands(sub)
    return parser


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _safe_json_loads(s: str | None, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _extract_dry_run_plan_from_run(run: dict) -> dict:
    """
    Best-effort: produce a plan-like object for dry_run without calling LLM/tools.

    We avoid side-effects:
      - no OpenAI calls
      - no tool execution
      - no new run persistence

    If run contains structured traces, we can surface them. Otherwise we fall back
    to objective + final answer snippet.
    """
    objective = run.get("objective") or ""

    # Try to surface a prior plan/steps if present in stored data.
    # Many systems store events like agent_plan_created or steps in a "trace" field.
    plan = {
        "objective": objective,
        "steps": [],
        "source": "best_effort",
    }

    # Common pattern: run["events"] is list of dict logs
    events = run.get("events")
    if isinstance(events, list):
        # Find last plan created
        plans = [
            e
            for e in events
            if e.get("event") in ("agent_plan_created", "plan_created")
        ]
        if plans:
            last = plans[-1]
            # "steps" could exist as list or be embedded differently
            if isinstance(last.get("steps"), list):
                plan["steps"] = last["steps"]
                plan["source"] = "recorded_events"

    # Some systems store tool steps explicitly
    steps = run.get("steps")
    if not plan["steps"] and isinstance(steps, list):
        plan["steps"] = steps
        plan["source"] = "run_steps"

    # Last fallback: if final answer exists, show it as context (no steps)
    if not plan["steps"]:
        final_answer = run.get("final_answer") or ""
        if final_answer:
            plan["final_answer_preview"] = final_answer[:300]

    return plan


def cmd_list(args) -> int:
    runs = list_runs(limit=args.limit)
    for r in runs:
        ts = format_ts(r.get("created_ts"))
        ok = "OK" if r.get("ok") else "FAIL"
        tokens = r.get("total_tokens") or 0
        cost = r.get("total_cost") or 0.0
        print(f"{ts} | {ok} | iter={r.get('iterations')} | tok={tokens} | ${cost:.4f}")
        print(f"  {r.get('run_id')}")
        obj = (r.get("objective") or "")[:120]
        print(f"  {obj}")
        print()
    return 0


def cmd_show(args) -> int:
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2
    _print_json(run)
    return 0


def cmd_replay(args) -> int:
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2

    objective = run.get("objective") or ""

    if args.dry_run:
        # Day 19 invariant: dry_run must have zero side effects:
        # - no OpenAI calls
        # - no tool execution
        # - no new run persistence
        plan = _extract_dry_run_plan_from_run(run)
        result = {
            "ok": True,
            "dry_run": True,
            "run_id": args.run_id,  # keep original
            "objective": objective,
            "plan": plan,
        }
        print(result)
        print(f"\nDRY_RUN: true")
        print(f"RUN_ID: {args.run_id}")
        return 0

    # Real replay: executes agent loop, creates a new run (as your current system does)
    client = OpenAIClient()
    registry = ToolRegistry()
    registry.register("summarize_text_local", summarize_text_local)

    result = run_agent_loop(
        client,
        registry,
        objective,
        max_iterations=3,
        dry_run=False,
    )

    payload = result.model_dump() if hasattr(result, "model_dump") else result
    print(payload)

    # PowerShell/CI-friendly: NEW_RUN_ID line for parsing
    run_id = getattr(result, "run_id", None)
    if run_id:
        print(f"\nNEW_RUN_ID: {run_id}")
    return 0


def cmd_compare(args) -> int:
    old_run = load_run(args.old_run_id)
    new_run = load_run(args.new_run_id)
    if not old_run or not new_run:
        print("Run not found")
        return 2

    old_ok = bool(old_run.get("ok"))
    new_ok = bool(new_run.get("ok"))

    old_tokens = old_run.get("total_tokens") or 0
    new_tokens = new_run.get("total_tokens") or 0
    old_cost = old_run.get("total_cost") or 0.0
    new_cost = new_run.get("total_cost") or 0.0

    sim = jaccard_similarity(
        old_run.get("final_answer") or "", new_run.get("final_answer") or ""
    )
    if not old_run.get("final_answer") or not new_run.get("final_answer"):
        print("Note: one or both runs missing final_answer; similarity may be low.")

    if (old_run.get("objective") or "") != (new_run.get("objective") or ""):
        print("WARNING: objectives differ between runs.")

    print("OK:", old_ok, "->", new_ok)
    print("Iterations:", old_run.get("iterations"), "->", new_run.get("iterations"))
    print("Tokens:", old_tokens, "->", new_tokens, "Δ", (new_tokens - old_tokens))
    print("Cost:", old_cost, "->", new_cost, "Δ", (new_cost - old_cost))
    print("Final answer similarity (Jaccard):", round(sim, 3))
    return 0


def cmd_judge(args) -> int:
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2

    client = OpenAIClient()
    report = judge_run(client, run, judge_model=args.model)

    # Day 19 invariant: judge must be persisted
    save_judge_eval(args.run_id, report)

    _print_json(report)
    return 0


def cmd_compare_judge(args) -> int:
    old = load_judge_eval(args.old_run_id)
    new = load_judge_eval(args.new_run_id)
    if not old or not new:
        print("Missing judge report. Run judge on both run_ids first.")
        return 2

    for k in [
        "overall",
        "correctness",
        "completeness",
        "concision",
        "clarity",
        "safety",
    ]:
        print(f"{k}: {old[k]:.3f} -> {new[k]:.3f}  Δ {(new[k]-old[k]):+.3f}")
    return 0


def cmd_gate_judge(args) -> int:
    # 1) Load run first
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2

    # 2) Load judge report; auto-judge if requested
    report = load_judge_eval(args.run_id)
    if not report:
        if not getattr(args, "auto_judge", False):
            print("Missing judge report. Run judge on this run_id first.")
            return 2

        try:
            client = OpenAIClient()
            report = judge_run(client, run, judge_model=args.judge_model)
            save_judge_eval(args.run_id, report)
            print(
                f"NOTE: judge report created via --auto_judge (model={args.judge_model})"
            )
        except Exception as e:
            print(f"ERROR: auto_judge failed: {e}")
            return 2

    # 3) Handle --min_score alias
    min_overall = args.min_overall
    if args.min_score is not None:
        min_overall = args.min_score

    cost = float(run.get("total_cost") or 0.0)

    thresholds = {
        "min_overall": min_overall,
        "min_correctness": args.min_correctness,
        "min_safety": args.min_safety,
        "max_cost": args.max_cost,
    }

    # 4) Evaluate gate
    fail_reasons = []

    if float(report.get("overall", 0.0)) < min_overall:
        fail_reasons.append(f"overall {report['overall']:.3f} < {min_overall:.3f}")

    if float(report.get("correctness", 0.0)) < args.min_correctness:
        fail_reasons.append(
            f"correctness {report['correctness']:.3f} < {args.min_correctness:.3f}"
        )

    if float(report.get("safety", 0.0)) < args.min_safety:
        fail_reasons.append(f"safety {report['safety']:.3f} < {args.min_safety:.3f}")

    if cost > args.max_cost:
        fail_reasons.append(f"cost ${cost:.4f} > ${args.max_cost:.4f}")

    failed = bool(fail_reasons)

    # 4.5) Optional JSON output for CI
    if args.json:
        result = {
            "run_id": args.run_id,
            "status": "FAIL" if failed else "PASS",
            "fail_reasons": fail_reasons,
            "thresholds": thresholds,
            "scores": {
                "overall": report.get("overall"),
                "correctness": report.get("correctness"),
                "completeness": report.get("completeness"),
                "concision": report.get("concision"),
                "clarity": report.get("clarity"),
                "safety": report.get("safety"),
            },
            "judge_model": report.get("judge_model"),
            "cost": cost,
            "notify": {
                "emails": [
                    e.strip() for e in (args.notify_email or "").split(",") if e.strip()
                ],
                "notify_on": args.notify_on,
                "dry_run": bool(args.notify_dry_run),
            },
        }
        print(json.dumps(result, ensure_ascii=False))

    # 5) Notifications (non-blocking)
    notify_emails = [
        e.strip() for e in (args.notify_email or "").split(",") if e.strip()
    ]

    if notify_emails:
        notify = (
            args.notify_on == "always"
            or (args.notify_on == "fail" and failed)
            or (args.notify_on == "pass" and not failed)
        )

        if notify:
            email = build_gate_judge_email(
                run=run,
                judge_report=report,
                thresholds=thresholds,
                fail_reasons=fail_reasons,
            )

            if args.notify_dry_run:
                print("\n--- NOTIFY (DRY RUN) ---")
                print("TO:", ", ".join(notify_emails))
                print("SUBJECT:", email["subject"])
                print(email["body"])
            else:
                cfg = load_smtp_config_from_env()
                if cfg:
                    try:
                        EmailNotifier(cfg).send(
                            email["subject"],
                            email["body"],
                            notify_emails,
                        )
                    except Exception as e:
                        print(f"NOTE: notification failed (ignored): {e}")
                else:
                    print("NOTE: notification skipped (missing SMTP config)")

    # 6) Exit code
    if failed:
        print("FAIL: gate_judge failed")
        return 1

    print("PASS: gate_judge ok")
    return 0


def cmd_export(args) -> int:
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2

    # Parse json fields stored as TEXT in SQLite
    state = _safe_json_loads(run.get("state_json"), default={})
    steps = _safe_json_loads(run.get("steps_json"), default=[])
    memory_used = _safe_json_loads(run.get("memory_used_json"), default=[])

    # Load optional attachments
    judge = load_judge_eval(args.run_id)  # may be None
    ev = load_eval(args.run_id)  # may be None

    # Build the run object (small by default)
    run_obj = {
        "run_id": run.get("run_id"),
        "created_ts": run.get("created_ts"),
        "objective": run.get("objective"),
        "ok": bool(run.get("ok")),
        "iterations": run.get("iterations"),
        "final_answer": run.get("final_answer"),
        "total_tokens": run.get("total_tokens"),
        "total_cost": run.get("total_cost"),
    }

    # Optionally include raw JSON strings (bigger export)
    if getattr(args, "include_raw_json", False):
        run_obj.update(
            {
                "state_json": run.get("state_json"),
                "steps_json": run.get("steps_json"),
                "memory_used_json": run.get("memory_used_json"),
            }
        )

    bundle = {
        "export_meta": {
            "exported_ts": time.time(),
            "exported_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": args.run_id,
            "tool": "autoops.tools.runs export",
        },
        "run": run_obj,
        "parsed": {
            "state": state,
            "steps": steps,
            "memory_used": memory_used,
        },
        "judge_eval": judge,
        "eval": ev,
    }

    # Determine output path
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path("data") / "exports" / f"{args.run_id}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)

    print(str(out_path))
    return 0


def cmd_eval(args) -> int:
    run = load_run(args.run_id)
    if not run:
        print("Run not found")
        return 2
    report = evaluate_run(run, cost_budget=args.budget)
    save_eval(args.run_id, report)
    _print_json(report)
    return 0


def cmd_compare_eval(args) -> int:
    old_run = load_run(args.old_run_id)
    new_run = load_run(args.new_run_id)
    if not old_run or not new_run:
        print("Run not found")
        return 2

    old = load_eval(args.old_run_id) or evaluate_run(old_run)
    new = load_eval(args.new_run_id) or evaluate_run(new_run)

    print(
        "quality:",
        old["quality_score"],
        "->",
        new["quality_score"],
        "Δ",
        new["quality_score"] - old["quality_score"],
    )
    print(
        "structure:",
        old["structure_score"],
        "->",
        new["structure_score"],
        "Δ",
        new["structure_score"] - old["structure_score"],
    )
    print(
        "cost:",
        old["cost_score"],
        "->",
        new["cost_score"],
        "Δ",
        new["cost_score"] - old["cost_score"],
    )
    print(
        "stability:",
        old["stability_score"],
        "->",
        new["stability_score"],
        "Δ",
        new["stability_score"] - old["stability_score"],
    )
    return 0


def cmd_memory_search(args) -> int:
    mem = find_relevant_runs(args.objective, k=args.k, scan_limit=args.scan_limit)
    _print_json(mem)
    return 0


def cmd_gate(args) -> int:
    old_run = load_run(args.old_run_id)
    new_run = load_run(args.new_run_id)
    if not old_run or not new_run:
        print("Run not found")
        return 2

    old = load_eval(args.old_run_id) or evaluate_run(old_run)
    new = load_eval(args.new_run_id) or evaluate_run(new_run)

    quality_drop = old["quality_score"] - new["quality_score"]

    old_cost = float(old_run.get("total_cost") or 0.0)
    new_cost = float(new_run.get("total_cost") or 0.0)
    if old_cost > 0:
        cost_increase_pct = ((new_cost - old_cost) / old_cost) * 100.0
    elif new_cost > 0:
        cost_increase_pct = 999.0
    else:
        cost_increase_pct = 0.0

    ok_regressed = bool(old_run.get("ok")) and not bool(new_run.get("ok"))

    failed = False
    if quality_drop > args.max_quality_drop:
        print(
            f"FAIL: quality dropped by {quality_drop:.3f} (> {args.max_quality_drop:.3f})"
        )
        failed = True
    if cost_increase_pct > args.max_cost_increase_pct:
        print(
            f"FAIL: cost increased by {cost_increase_pct:.1f}% (> {args.max_cost_increase_pct:.1f}%)"
        )
        failed = True
    if ok_regressed:
        print("FAIL: run regressed from OK to FAIL")
        failed = True

    if failed:
        return 1

    print("PASS: no regression detected")
    return 0


def dispatch(args) -> int:
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "replay":
        return cmd_replay(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    if args.cmd == "judge":
        return cmd_judge(args)
    if args.cmd == "compare_judge":
        return cmd_compare_judge(args)
    if args.cmd == "gate_judge":
        return cmd_gate_judge(args)
    if args.cmd == "eval":
        return cmd_eval(args)
    if args.cmd == "compare_eval":
        return cmd_compare_eval(args)
    if args.cmd == "memory_search":
        return cmd_memory_search(args)
    if args.cmd == "gate":
        return cmd_gate(args)
    if args.cmd == "export":
        return cmd_export(args)

    print(f"Unknown command: {args.cmd}")
    return 2


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(dispatch(args))


if __name__ == "__main__":
    main()
