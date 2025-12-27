import json
from unittest import result

from autoops.infra.ids import new_run_id
from autoops.infra.logging import log_event
from autoops.core.prompt_loader import load_prompt
from autoops.core.agent_schemas import Plan
from autoops.core.agent_executor import execute_plan
from autoops.core.agent_loop_schemas import AgentState, DoneCheck, AgentRunResult
from autoops.core.tool_router import ToolRegistry
from autoops.infra.storage import save_run


def _format_notes(notes: list[str]) -> str:
    return "\n".join(f"- {n}" for n in notes) if notes else "- (none)"


def run_agent_loop(
    client,
    registry: ToolRegistry,
    objective: str,
    *,
    max_iterations: int = 3,
    planner_version: str = "v1",
    done_check_version: str = "v1",
) -> AgentRunResult:
    """
    Reason:
    - Implements Plan -> Execute -> Observe -> Replan loop.
    Benefit:
    - Agent adapts based on tool results and stops deterministically.
    """
    run_id = new_run_id()
    state = AgentState()
    executed_steps_log: list[dict] = []
    final_answer = None

    log_event(
        "agent_loop_start",
        run_id=run_id,
        objective=objective,
        max_iterations=max_iterations,
    )

    for iteration in range(1, max_iterations + 1):
        log_event("agent_iteration_start", run_id=run_id, iteration=iteration)

        # 1) Create plan from replanner (uses state)
        replanner_prompt = load_prompt(
            "replanner",
            version=planner_version,
            objective=objective,
            notes=_format_notes(state.notes),
            last_tool_results=json.dumps(state.last_tool_results, ensure_ascii=False),
        )
        plan = client.generate_structured(replanner_prompt, Plan)

        log_event(
            "agent_plan_created",
            run_id=run_id,
            iteration=iteration,
            steps=len(plan.steps),
        )

        # 2) Execute plan
        summary = execute_plan(registry, plan, run_id=run_id)

        # 3) Observe: update state from tool results
        for step in summary.steps:
            if step.ok:
                state.last_tool_results.append(
                    {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "data": step.data,
                    }
                )
                state.notes.append(f"Step {step.step_id} ({step.tool_name}) succeeded.")
                executed_steps_log.extend([s.model_dump() for s in summary.steps])
            else:
                state.last_tool_results.append(
                    {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "error": step.error,
                    }
                )
                state.notes.append(
                    f"Step {step.step_id} ({step.tool_name}) failed: {step.error}"
                )
                executed_steps_log.extend([s.model_dump() for s in summary.steps])

        log_event(
            "agent_state_updated",
            run_id=run_id,
            iteration=iteration,
            notes_count=len(state.notes),
        )

        # 4) Done check
        done_prompt = load_prompt(
            "done_check",
            version=done_check_version,
            objective=objective,
            notes=_format_notes(state.notes),
        )
        done_check = client.generate_structured(done_prompt, DoneCheck)

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

            # Persist run
            save_run(
                run_id=run_id,
                objective=objective,
                ok=result.ok,
                iterations=result.iterations,
                final_answer=result.final_answer,
                state=result.state.model_dump(),
                steps=executed_steps_log,  # minimal step log; see Step 4 for full
                total_tokens=getattr(client, "total_tokens", None),
                total_cost=getattr(client, "total_cost", None),
            )

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
                steps=result.state.last_tool_results,
                total_tokens=getattr(client, "total_tokens", None),
                total_cost=getattr(client, "total_cost", None),
            )

    return result
