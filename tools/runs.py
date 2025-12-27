import argparse
import json
from autoops.infra.storage import list_runs, load_run


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=20)

    p_show = sub.add_parser("show")
    p_show.add_argument("run_id")

    args = parser.parse_args()

    if args.cmd == "list":
        runs = list_runs(limit=args.limit)
        for r in runs:
            print(r["run_id"], r["ok"], r["iterations"], r.get("total_tokens"), r.get("total_cost"))
            print("  ", r["objective"][:120])
    elif args.cmd == "show":
        run = load_run(args.run_id)
        if not run:
            print("Run not found")
            return
        print(json.dumps(run, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
