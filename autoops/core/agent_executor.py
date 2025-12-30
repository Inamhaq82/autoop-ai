from autoops.infra.logging import log_event
from autoops.core.agent_schemas import Plan, RunSummary, StepExecution
from autoops.core.tool_router import ToolRegistry


def execute_plan(registry: ToolRegistry, plan: Plan, *, run_id: str) -> RunSummary:
    """
    Reason:
    - Central executor that runs validated plans step-by-step.
    Benefit:
    - Predictable agent behavior with clean logging and failure handling.
    """
    # ✅ Use the run_id passed from run_agent_loop (do NOT overwrite it)
    log_event("agent_run_start", run_id=run_id, objective=plan.objective)

    executed_steps: list[StepExecution] = []
    overall_ok = True

    for step in plan.steps:
        log_event(
            "agent_step_start",
            run_id=run_id,
            step_id=step.step_id,
            tool_name=step.tool_name,
            args_keys=list(step.args.keys()),
        )

        # Your registry.run() expects something with .tool_name and .args
        # Plan step likely has these, so this is fine.
        result = registry.run(step)

        executed_steps.append(
            StepExecution(
                step_id=step.step_id,
                tool_name=step.tool_name,
                ok=result.ok,
                data=result.data,
                error=result.error,
            )
        )

        log_event(
            "agent_step_end",
            run_id=run_id,
            step_id=step.step_id,
            tool_name=step.tool_name,
            ok=result.ok,
            error=result.error,
        )

        if not result.ok:
            overall_ok = False
            break  # fail-fast for now

    summary = RunSummary(objective=plan.objective, ok=overall_ok, steps=executed_steps)
    log_event("agent_run_end", run_id=run_id, ok=summary.ok, steps=len(summary.steps))
    return summary
