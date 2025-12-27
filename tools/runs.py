import argparse
import json
from autoops.infra.storage import list_runs, load_run
from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.tools.text_tools import summarize_text_local
from autoops.core.agent_loop import run_agent_loop
import datetime as dt
from autoops.infra.storage import save_eval, load_eval
from autoops.core.evaluator import evaluate_run


def jaccard_similarity(a: str, b: str) -> float:
    sa = set(a.lower().split()) if a else set()
    sb = set(b.lower().split()) if b else set()
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def format_ts(ts: float | None) -> str:
    """
    Convert unix timestamp -> human readable local time.
    """
    if not ts:
        return "UNKNOWN_TIME"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=20)

    p_show = sub.add_parser("show")
    p_show.add_argument("run_id")

    p_replay = sub.add_parser("replay")
    p_replay.add_argument("run_id")

    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("old_run_id")
    p_cmp.add_argument("new_run_id")

    p_eval = sub.add_parser("eval")
    p_eval.add_argument("run_id")
    p_eval.add_argument("--budget", type=float, default=0.05)

    p_ce = sub.add_parser("compare_eval")
    p_ce.add_argument("old_run_id")
    p_ce.add_argument("new_run_id")

    p_gate = sub.add_parser("gate")
    p_gate.add_argument("old_run_id")
    p_gate.add_argument("new_run_id")
    p_gate.add_argument("--max_quality_drop", type=float, default=0.10)
    p_gate.add_argument("--max_cost_increase_pct", type=float, default=50.0)

    args = parser.parse_args()

    if args.cmd == "list":
        runs = list_runs(limit=args.limit)
        for r in runs:
            ts = format_ts(r.get("created_ts"))
            ok = "OK" if r["ok"] else "FAIL"
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

        result = run_agent_loop(client, registry, objective, max_iterations=3)
        print(result.model_dump() if hasattr(result, "model_dump") else result)
        if hasattr(result, "run_id"):
            print("\nNEW_RUN_ID:", result.run_id)

    elif args.cmd == "compare":
        old_run = load_run(args.old_run_id)
        new_run = load_run(args.new_run_id)
        if not old_run or not new_run:
            print("Run not found")
            return
        old_ok = bool(old_run["ok"])
        new_ok = bool(new_run["ok"])

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
    elif args.cmd == "eval":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return
        report = evaluate_run(run, cost_budget=args.budget)
        save_eval(args.run_id, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.cmd == "compare_eval":
        old = load_eval(args.old_run_id) or evaluate_run(load_run(args.old_run_id))
        new = load_eval(args.new_run_id) or evaluate_run(load_run(args.new_run_id))
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

    elif args.cmd == "gate":
        old_run = load_run(args.old_run_id)
        new_run = load_run(args.new_run_id)
        if not old_run or not new_run:
            print("Run not found")
            raise SystemExit(2)

        old = load_eval(args.old_run_id) or evaluate_run(old_run)
        new = load_eval(args.new_run_id) or evaluate_run(new_run)

        # Gates
        quality_drop = old["quality_score"] - new["quality_score"]
        cost_increase_pct = 0.0
        old_cost = float(old_run.get("total_cost") or 0.0)
        new_cost = float(new_run.get("total_cost") or 0.0)
        if old_cost > 0:
            cost_increase_pct = ((new_cost - old_cost) / old_cost) * 100.0
        elif new_cost > 0:
            cost_increase_pct = 999.0

        ok_regressed = bool(old_run["ok"]) and not bool(new_run["ok"])

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
