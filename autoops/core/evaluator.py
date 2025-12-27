from __future__ import annotations
from typing import Dict, Any, Set
from autoops.core.eval_schemas import EvalReport


def _tokens(text: str) -> Set[str]:
    return set((text or "").lower().split())


def jaccard(a: str, b: str) -> float:
    sa = _tokens(a)
    sb = _tokens(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def evaluate_run(run: Dict[str, Any], *, cost_budget: float = 0.05) -> Dict[str, Any]:
    """
    Deterministic evaluation (no LLM).
    """
    run_id = run["run_id"]
    objective = run.get("objective") or ""
    final_answer = run.get("final_answer") or ""
    ok = bool(run.get("ok"))
    iterations = int(run.get("iterations") or 0)
    total_cost = float(run.get("total_cost") or 0.0)

    reasons: list[str] = []

    # Quality: overlap between objective and answer terms (cheap proxy)
    quality = jaccard(objective, final_answer)
    if quality < 0.2:
        reasons.append("Low objective/answer overlap (quality proxy).")

    # Structure: must have final_answer and decent length
    structure = 1.0
    if not final_answer.strip():
        structure = 0.0
        reasons.append("Missing final_answer.")
    elif len(final_answer.strip()) < 20:
        structure = 0.4
        reasons.append("final_answer is very short.")

    # Cost: 1.0 when <= budget, decreases beyond
    if cost_budget <= 0:
        cost_score = 1.0
    else:
        cost_ratio = total_cost / cost_budget
        cost_score = clamp01(1.0 - (cost_ratio - 1.0) * 0.5)  # penalize above budget
        if total_cost > cost_budget:
            reasons.append(f"Cost {total_cost:.4f} exceeds budget {cost_budget:.4f}.")

    # Stability: ok + fewer iterations = better
    stability = 1.0 if ok else 0.0
    if ok and iterations > 1:
        stability = clamp01(1.0 - (iterations - 1) * 0.2)
        reasons.append("Multiple iterations used (stability penalty).")

    report = EvalReport(
        run_id=run_id,
        quality_score=float(clamp01(quality)),
        structure_score=float(clamp01(structure)),
        cost_score=float(clamp01(cost_score)),
        stability_score=float(clamp01(stability)),
        reasons=reasons,
    )
    return report.model_dump()
