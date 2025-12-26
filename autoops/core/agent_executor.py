from autoops.infra.logging import log_event
from autoops.core.agent_schemas import Plan, RunSummary, StepExecution
from autoops.core.tool_router import ToolRegistry
from autoops.infra.ids import new_run_id


def execute_plan(registry: ToolRegistry, plan: Plan) -> RunSummary:
    """
    Reason:
    - Central executor that runs validated plans step-by-step.
    Benefit:
    - Predictable agent behavior with clean logging and failure handling.
    """
    run_id = new_run_id()
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

        result = registry.run(step)  # <-- not compatible yet; we fix in Step 4

        # Step 4 will adapt registry.run() to accept PlanStep or ToolRequest
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
            break  # fail-fast for now (safe default)

    summary = RunSummary(objective=plan.objective, ok=overall_ok, steps=executed_steps)
    log_event("agent_run_end", run_id=run_id, ok=summary.ok, steps=len(summary.steps))
    return summary
