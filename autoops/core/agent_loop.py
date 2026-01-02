import json

from autoops.infra.ids import new_run_id
from autoops.infra.logging import log_event
from autoops.core.prompt_loader import load_prompt
from autoops.core.agent_schemas import Plan
from autoops.core.agent_executor import execute_plan
from autoops.core.agent_loop_schemas import AgentState, DoneCheck, AgentRunResult
from autoops.core.tool_router import ToolRegistry
from autoops.infra.storage import save_run, migrate_db
from autoops.core.memory import find_relevant_runs, format_memories


def _format_notes(notes: list[str]) -> str:
    return "\n".join(f"- {n}" for n in notes) if notes else "- (none)"


def deterministic_done_check(
    objective: str, latest_tool_result: dict | None
) -> DoneCheck:
    """
    Deterministic completion checker (no LLM).

    Stop conditions are control logic; LLMs are not reliable for control flow.
    """
    if not latest_tool_result:
        return DoneCheck(done=False, rationale="No tool result available yet.")

    data = latest_tool_result.get("data") or {}
    summary = data.get("summary")
    key_points = data.get("key_points")

    if not isinstance(summary, str) or not summary.strip():
        return DoneCheck(done=False, rationale="Missing data.summary.")
    if not isinstance(key_points, list) or len(key_points) < 2:
        return DoneCheck(
            done=False, rationale="Missing data.key_points (need at least 2)."
        )

    # If objective mentions 2 sentences, accept 1–3 sentences (practical)
    if "2 sentence" in objective.lower():
        sentence_count = len(
            [
                s
                for s in summary.replace("!", ".").replace("?", ".").split(".")
                if s.strip()
            ]
        )
        if sentence_count < 1 or sentence_count > 3:
            return DoneCheck(
                done=False,
                rationale=f"Summary sentence count out of range (got {sentence_count}, expected 1–3).",
            )

    rationale = f"SUMMARY: {summary.strip()}\n" f"KEY POINTS:\n- " + "\n- ".join(
        str(k).strip() for k in key_points if str(k).strip()
    )
    return DoneCheck(done=True, rationale=rationale)


def run_agent_loop(
    client,
    registry: ToolRegistry,
    objective: str,
    *,
    max_iterations: int = 3,
    dry_run: bool = False,
    planner_version: str = "v2",
) -> AgentRunResult:
    """
    Plan -> Execute -> Observe -> Replan loop with deterministic stopping.
    """
    run_id = new_run_id()

    # Ensure DB migrations are applied (memory_used_json, etc.)
    migrate_db()

    # Compute objective payload once per run (stable input)
    objective_payload = (
        objective.split(":", 1)[1].strip() if ":" in objective else objective
    )

    # State must exist before any early returns (dry_run)
    state = AgentState()
    executed_steps_log: list[dict] = []
    final_answer: str | None = None

    # Retrieve memory once per run
    memories = find_relevant_runs(objective, k=3, scan_limit=50)
    memory_used = [m["run_id"] for m in memories]
    memories_text = format_memories(memories)

    log_event(
        "memory_retrieved", run_id=run_id, count=len(memories), memory_used=memory_used
    )

    log_event(
        "agent_loop_start",
        run_id=run_id,
        objective=objective,
        max_iterations=max_iterations,
        dry_run=dry_run,
    )

    for iteration in range(1, max_iterations + 1):
        log_event("agent_iteration_start", run_id=run_id, iteration=iteration)

        # 1) Create plan
        replanner_prompt = load_prompt(
            "replanner",
            version=planner_version,
            objective=objective,
            objective_payload=objective_payload,
            notes=_format_notes(state.notes),
            last_tool_results=json.dumps(state.last_tool_results, ensure_ascii=False),
            memories="(none)" if iteration == 1 else memories_text,
        )

        plan = client.generate_structured(replanner_prompt, Plan)

        log_event(
            "agent_plan_created",
            run_id=run_id,
            iteration=iteration,
            steps=len(plan.steps),
        )

        # Validate plan shape early
        if not plan.steps:
            state.notes.append("Planner returned empty steps.")
            if dry_run:
                return AgentRunResult(
                    run_id=run_id,
                    ok=False,
                    objective=objective,
                    iterations=iteration,
                    state=state,
                    final_answer="[DRY RUN] Empty plan generated.",
                )
            continue

        # Hard override + enforce objective payload constraint
        for step in plan.steps:
            if step.tool_name == "summarize_text_local":
                step.args["text"] = objective_payload
                step.args["max_sentences"] = 2

        # Strict payload enforcement (exact match)
        for step in plan.steps:
            if step.tool_name == "summarize_text_local":
                if step.args.get("text") != objective_payload:
                    raise RuntimeError(
                        "Planner violated objective payload constraint (text mismatch)."
                    )

        if dry_run:
            # Do not execute tools, do not save run; just return plan details
            log_event("dry_run_exit", run_id=run_id, iteration=iteration)
            return AgentRunResult(
                run_id=run_id,
                ok=True,
                objective=objective,
                iterations=iteration,
                state=state,
                final_answer=f"[DRY RUN] Plan: {plan.model_dump()}",
            )

        # 2) Execute plan
        summary = execute_plan(registry, plan, run_id=run_id)

        executed_steps_log.extend([s.model_dump() for s in summary.steps])

        # 3) Observe: update state
        for step_exec in summary.steps:
            if step_exec.ok:
                state.last_tool_results.append(
                    {
                        "step_id": step_exec.step_id,
                        "tool_name": step_exec.tool_name,
                        "data": step_exec.data,
                    }
                )
                state.notes.append(
                    f"Step {step_exec.step_id} ({step_exec.tool_name}) succeeded."
                )
            else:
                state.last_tool_results.append(
                    {
                        "step_id": step_exec.step_id,
                        "tool_name": step_exec.tool_name,
                        "error": step_exec.error,
                    }
                )
                state.notes.append(
                    f"Step {step_exec.step_id} ({step_exec.tool_name}) failed: {step_exec.error}"
                )

        log_event(
            "agent_state_updated",
            run_id=run_id,
            iteration=iteration,
            notes_count=len(state.notes),
        )

        latest_tool_result = (
            state.last_tool_results[-1] if state.last_tool_results else None
        )

        # 4) Deterministic done check
        done_check = deterministic_done_check(objective, latest_tool_result)

        log_event(
            "agent_done_check",
            run_id=run_id,
            iteration=iteration,
            done=done_check.done,
            rationale=done_check.rationale,
        )

        if done_check.done:
            final_answer = done_check.rationale

            result = AgentRunResult(
                run_id=run_id,
                ok=True,
                objective=objective,
                iterations=iteration,
                state=state,
                final_answer=final_answer,
            )

            save_run(
                run_id=run_id,
                objective=objective,
                ok=result.ok,
                iterations=result.iterations,
                final_answer=result.final_answer,
                state=result.state.model_dump(),
                steps=executed_steps_log,
                total_tokens=getattr(client, "total_tokens", None),
                total_cost=getattr(client, "total_cost", None),
                memory_used=memory_used,
            )

            return result

    # Exhausted iterations: persist failure + return
    result = AgentRunResult(
        run_id=run_id,
        ok=False,
        objective=objective,
        iterations=max_iterations,
        state=state,
        final_answer=final_answer,
    )

    save_run(
        run_id=run_id,
        objective=objective,
        ok=result.ok,
        iterations=result.iterations,
        final_answer=result.final_answer,
        state=result.state.model_dump(),
        steps=executed_steps_log,
        total_tokens=getattr(client, "total_tokens", None),
        total_cost=getattr(client, "total_cost", None),
        memory_used=memory_used,
    )

    log_event(
        "agent_run_summary",
        run_id=run_id,
        ok=result.ok,
        iterations=result.iterations,
        total_tokens=getattr(client, "total_tokens", None),
        total_cost=getattr(client, "total_cost", None),
    )

    return result
