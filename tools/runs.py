import argparse
import json
import datetime as dt

from autoops.infra.storage import (
    list_runs,
    load_run,
    save_eval,
    load_eval,
    save_judge_eval,
    load_judge_eval,
)
from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.tools.text_tools import summarize_text_local
from autoops.core.agent_loop import run_agent_loop
from autoops.core.evaluator import evaluate_run
from autoops.core.judge import judge_run
from autoops.core.memory import find_relevant_runs


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
    choices = getattr(subparsers, "choices", {}) or {}
    names = list(choices.keys())

    # "choices" is a dict so duplicates are rare, but collisions can happen with
    # repeated registration or aliasing.
    if len(names) != len(set(names)):
        raise SystemExit(f"Duplicate subcommand names detected: {names}")

    # Catch alias collisions if you use aliases=
    seen = set(names)
    for name, sp in choices.items():
        aliases = getattr(sp, "aliases", []) or []
        for a in aliases:
            if a in seen:
                raise SystemExit(
                    f"Alias collision: '{a}' already registered (while adding '{name}')"
                )
            seen.add(a)


def build_parser():
    parser = argparse.ArgumentParser(prog="autoops-runs")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # IMPORTANT: register subcommands only here
    # subparsers.add_parser("list", ...)
    # subparsers.add_parser("show", ...)
    # subparsers.add_parser("replay", ...)
    # subparsers.add_parser("judge", ...)
    # subparsers.add_parser("compare_judge", ...)
    # subparsers.add_parser("gate_judge", ...)

    assert_no_duplicate_subcommands(subparsers)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # list
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=20)

    # show
    p_show = sub.add_parser("show")
    p_show.add_argument("run_id")

    # compare
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("old_run_id")
    p_cmp.add_argument("new_run_id")

    # eval
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("run_id")
    p_eval.add_argument("--budget", type=float, default=0.05)

    # compare_eval
    p_ce = sub.add_parser("compare_eval")
    p_ce.add_argument("old_run_id")
    p_ce.add_argument("new_run_id")

    # gate (evaluator-based regression gate)
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("old_run_id")
    p_gate.add_argument("new_run_id")
    p_gate.add_argument("--max_quality_drop", type=float, default=0.10)
    p_gate.add_argument("--max_cost_increase_pct", type=float, default=50.0)

    # judge (LLM-based judge)
    p_judge = sub.add_parser("judge")
    p_judge.add_argument("run_id")
    p_judge.add_argument("--model", type=str, default="gpt-4o-mini")

    # compare_judge
    p_cj = sub.add_parser("compare_judge")
    p_cj.add_argument("old_run_id")
    p_cj.add_argument("new_run_id")

    # gate_judge (judge-based regression gate)
    p_gatej = sub.add_parser("gate_judge")
    p_gatej.add_argument("run_id")
    p_gatej.add_argument("--min_overall", type=float, default=0.80)
    p_gatej.add_argument("--min_correctness", type=float, default=0.85)
    p_gatej.add_argument("--min_safety", type=float, default=0.95)
    p_gatej.add_argument("--max_cost", type=float, default=0.05)

    p_replay = sub.add_parser("replay")
    p_replay.add_argument("run_id")
    p_replay.add_argument("--dry_run", action="store_true")

    # memory_search
    p_mem = sub.add_parser("memory_search")
    p_mem.add_argument("--objective", required=True)
    p_mem.add_argument("--k", type=int, default=3)
    p_mem.add_argument("--scan_limit", type=int, default=50)

    args = parser.parse_args()

    if args.cmd == "list":
        runs = list_runs(limit=args.limit)
        for r in runs:
            ts = format_ts(r.get("created_ts"))
            ok = "OK" if r.get("ok") else "FAIL"
            tokens = r.get("total_tokens") or 0
            cost = r.get("total_cost") or 0.0
            print(f"{ts} | {ok} | iter={r['iterations']} | tok={tokens} | ${cost:.4f}")
            print(f"  {r['run_id']}")
            print(f"  {r['objective'][:120]}")
            print()

    elif args.cmd == "show":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return
        print(json.dumps(run, indent=2, ensure_ascii=False))

    elif args.cmd == "replay":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return

        objective = run["objective"]

        client = OpenAIClient()
        registry = ToolRegistry()
        registry.register("summarize_text_local", summarize_text_local)

        result = run_agent_loop(
            client,
            registry,
            objective,
            max_iterations=3,
            dry_run=args.dry_run,
        )
        print(result.model_dump() if hasattr(result, "model_dump") else result)
        if hasattr(result, "run_id"):
            print("\nNEW_RUN_ID:", result.run_id)

    elif args.cmd == "compare":
        old_run = load_run(args.old_run_id)
        new_run = load_run(args.new_run_id)
        if not old_run or not new_run:
            print("Run not found")
            return

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
        print("Iterations:", old_run["iterations"], "->", new_run["iterations"])
        print("Tokens:", old_tokens, "->", new_tokens, "Δ", (new_tokens - old_tokens))
        print("Cost:", old_cost, "->", new_cost, "Δ", (new_cost - old_cost))
        print("Final answer similarity (Jaccard):", round(sim, 3))

    elif args.cmd == "judge":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return

        client = OpenAIClient()
        report = judge_run(client, run, judge_model=args.model)
        save_judge_eval(args.run_id, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.cmd == "compare_judge":
        old = load_judge_eval(args.old_run_id)
        new = load_judge_eval(args.new_run_id)
        if not old or not new:
            print("Missing judge report. Run judge on both run_ids first.")
            return

        for k in [
            "overall",
            "correctness",
            "completeness",
            "concision",
            "clarity",
            "safety",
        ]:
            print(f"{k}: {old[k]:.3f} -> {new[k]:.3f}  Δ {(new[k]-old[k]):+.3f}")

    elif args.cmd == "gate_judge":
        report = load_judge_eval(args.run_id)
        if not report:
            print("Missing judge report. Run judge on this run_id first.")
            raise SystemExit(2)

        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            raise SystemExit(2)

        cost = float(run.get("total_cost") or 0.0)

        failed = False
        if report["overall"] < args.min_overall:
            print(f"FAIL: overall {report['overall']:.3f} (< {args.min_overall:.3f})")
            failed = True
        if report["correctness"] < args.min_correctness:
            print(
                f"FAIL: correctness {report['correctness']:.3f} (< {args.min_correctness:.3f})"
            )
            failed = True
        if report["safety"] < args.min_safety:
            print(f"FAIL: safety {report['safety']:.3f} (< {args.min_safety:.3f})")
            failed = True
        if cost > args.max_cost:
            print(f"FAIL: cost ${cost:.4f} (> ${args.max_cost:.4f})")
            failed = True

        if failed:
            raise SystemExit(1)

        print("PASS: gate_judge ok")

    elif args.cmd == "eval":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return
        report = evaluate_run(run, cost_budget=args.budget)
        save_eval(args.run_id, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.cmd == "compare_eval":
        old_run = load_run(args.old_run_id)
        new_run = load_run(args.new_run_id)
        if not old_run or not new_run:
            print("Run not found")
            return

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

    elif args.cmd == "memory_search":
        mem = find_relevant_runs(args.objective, k=args.k, scan_limit=args.scan_limit)
        print(json.dumps(mem, indent=2, ensure_ascii=False))

    elif args.cmd == "gate":
        old_run = load_run(args.old_run_id)
        new_run = load_run(args.new_run_id)
        if not old_run or not new_run:
            print("Run not found")
            raise SystemExit(2)

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
            raise SystemExit(1)

        print("PASS: no regression detected")


if __name__ == "__main__":
    main()
