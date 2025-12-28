import json
from typing import Any, Dict

from autoops.core.prompt_loader import load_prompt
from autoops.core.judge_schemas import JudgeReport


def judge_run(client, run: Dict[str, Any], *, judge_model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """
    Reason:
    - LLM-based rubric scoring catches quality regressions beyond heuristics.
    Benefit:
    - More human-aligned evaluation while staying structured.
    """
    run_id = run["run_id"]
    objective = run.get("objective") or ""
    final_answer = run.get("final_answer") or ""

    # Keep steps summary short (avoid huge prompt)
    steps_json = run.get("steps_json") or "[]"
    try:
        steps = json.loads(steps_json)
    except Exception:
        steps = []

    steps_summary = ""
    if steps:
        # summarize first few steps only
        parts = []
        for s in steps[:6]:
            tool = s.get("tool_name")
            ok = s.get("ok")
            parts.append(f"{tool} ok={ok}")
        steps_summary = "; ".join(parts)
    else:
        steps_summary = "(none)"

    prompt = load_prompt(
        "judge",
        version="v1",
        run_id=run_id,
        objective=objective[:1000],
        final_answer=final_answer[:3000],
        steps_summary=steps_summary,
    )

    # Temporarily override the client's model for judging (safe, reversible)
    original_model = getattr(client, "model", None)
    client.model = judge_model  # your client uses self.model

    report = client.generate_structured(prompt, JudgeReport)

    # Restore
    if original_model is not None:
        client.model = original_model

    return report.model_dump()
