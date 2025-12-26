from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """
    Reason:
    - A single atomic step the executor can run.
    Benefit:
    - You can validate and execute step-by-step deterministically.
    """
    step_id: int = Field(ge=1)
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """
    Reason:
    - The model must output a structured, executable plan.
    Benefit:
    - Eliminates ad-hoc parsing and makes agent behavior testable.
    """
    objective: str
    steps: List[PlanStep]


class StepExecution(BaseModel):
    """
    Captures what happened for each executed step.
    """
    step_id: int
    tool_name: str
    ok: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class RunSummary(BaseModel):
    """
    Reason:
    - Standardize the final output of an agent run.
    Benefit:
    - Easy to persist to DB later and compare runs.
    """
    objective: str
    ok: bool
    steps: List[StepExecution]
